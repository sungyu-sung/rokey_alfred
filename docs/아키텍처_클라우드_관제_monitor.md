# 외부 인터넷 관제 아키텍처 (monitor_server 중심)

> 목표: 외부 와이파이/인터넷에서 관제 대시보드를 **동적으로** 보고 싶다.
> 전제(확정): **별도 클라우드 SQL DB를 새로 만들지 않는다.** 로컬 `monitor_server`가
> DB이자 백엔드 = **단일 진실원천(source of truth)** 으로 유지한다. ("로컬 db = monitor db 서버")

---

## 1. 왜 이 구조인가 — 핵심 제약

ROS2(DDS)는 **로컬 멀티캐스트 전용**이라 클라우드에서 직접 구독할 수 없다.
현재 [monitor_server/ros_ingest.py](../monitor_server/ros_ingest.py)가 LAN 안에서 ROS를
구독해 로컬 DB([monitor_server/db.py](../monitor_server/db.py), SQLite/WAL)에 적재한다.

따라서 데이터의 길은 그대로 두고 — **로컬 monitor_server를 인터넷에서 안전하게 접근**하게
만들고, 화면(프론트)만 Vercel로 올린다. 클라우드에 DB를 두지 않으므로 스키마 이중관리·동기화
지연·쓰기 폭주 문제가 모두 사라진다.

---

## 2. 시스템 아키텍처

```
┌─ 로봇 LAN (현장) ──────────────────────────────────────────────┐
│                                                                │
│  robot2 / robot4  ──DDS──▶  monitor_server (로컬, 상주)         │
│                              • ros_ingest: ROS2 구독            │
│                              • db.py: SQLite(fms.db, WAL)  ◀── 단일 DB
│                              • api.py: Flask :5000 (REST+세션)  │
│                                       ▲                         │
│                              cloudflared (아웃바운드 터널)       │
└───────────────────────────────────────┼───────────────────────┘
                                         │ HTTPS (아웃바운드 전용,
                                         │ 인바운드 포트개방 없음)
                                         ▼
                         ┌─ Cloudflare Edge ─┐
                         │  monitor.도메인.com │  ← 공개 HTTPS + TLS 자동
                         │  (Cloudflare Access│     선택: 접근 게이트)
                         └─────────┬──────────┘
                    REST /api/*    │   (정적은 Vercel에서)
                                   ▼
                         ┌─ Vercel (클라우드) ─┐
                         │  대시보드 정적 SPA   │  ← dashboard.html 이식
                         │  API_BASE = 터널URL  │
                         └─────────┬───────────┘
                                   ▲ 외부 인터넷/와이파이
                              관제 브라우저 (어디서나)
```

핵심: **monitor_server는 LAN 안에 그대로**, 바깥으로 나가는 터널 하나만 추가. 로봇 네트워크에
인바운드 구멍을 내지 않는다(현재 Flask를 `0.0.0.0:5000`으로 직접 노출하는 것보다 훨씬 안전).

---

## 3. 구성요소별 역할

| 구성요소 | 위치 | 역할 | 변경량 |
|---|---|---|---|
| ROS2 (robot2/4) | LAN | 상태·이벤트·검출·IF-01 발행 | 없음 |
| monitor_server | 로컬 상주 | ROS 적재 + DB + REST API + 세션 인증 | 소폭(보안 설정) |
| **터널(cloudflared)** | 로컬 | monitor_server를 공개 HTTPS로 노출(아웃바운드) | 신규 |
| **Vercel** | 클라우드 | 대시보드 정적 호스팅, 터널 API 소비 | 신규(프론트 이식) |
| Cloudflare Access(선택) | 엣지 | 로그인 앞단 추가 게이트 | 선택 |

---

## 4. "동적"을 어떻게 줄 것인가

현재 대시보드는 2초 폴링이다([dashboard.html](../monitor_server/web/dashboard.html), `setInterval(load, 2000)`).
터널을 통해도 그대로 동작하므로 **1차 릴리스는 폴링 유지가 가장 간단**하다.

더 즉각적인 푸시가 필요하면 단계적으로:
- **SSE(Server-Sent Events)** — Flask에서 `text/event-stream` 엔드포인트 1개 추가. 단방향
  푸시라 관제 대시보드에 적합하고 터널 친화적. (권장 2단계)
- WebSocket — 양방향이 필요할 때만.

별도 클라우드 Realtime(Supabase 등)을 쓰지 않으므로, 푸시는 monitor_server가 직접 담당한다.

---

## 5. 외부 공개 시 반드시 처리할 보안 (현 코드 기준)

현재 [api.py](../monitor_server/api.py) / [config.py](../monitor_server/config.py) 상태:
세션 쿠키 인증(admin), `CORS_ORIGINS="*"`, `ADMIN_PASSWORD="admin1234"`, `SECRET_KEY=""`(미설정 시 매 재시작마다 랜덤).

인터넷 노출 전 체크리스트:
1. **`FMS_SECRET_KEY` 고정 설정** — 미설정이면 재시작 때마다 세션 무효화.
2. **관리자 비밀번호 교체** — `FMS_ADMIN_PASSWORD` 강한 값으로.
3. **CORS를 Vercel 도메인으로 제한** — `FMS_CORS_ORIGINS=https://<프로젝트>.vercel.app`
   (`*` 유지 금지).
4. **크로스사이트 쿠키 처리** — Vercel(프론트)과 터널(API)이 다른 도메인이면 세션 쿠키에
   `SameSite=None; Secure` 필요. 그렇지 않으면 토큰 기반(헤더) 인증으로 전환 검토.
5. **TLS는 터널이 제공** — Flask를 평문 노출하지 말 것.
6. (선택) **Cloudflare Access**로 로그인 앞단에 한 겹 더(이메일 허용목록/SSO).

> 대안(가장 단순): 프론트를 Vercel로 분리하지 않고 **dashboard를 Flask가 계속 서빙**하면
> 동일 출처라 4번(크로스사이트 쿠키)·3번(CORS) 문제가 사라진다. 이때 Vercel은 불필요하고
> 터널 URL 하나로 끝난다. "Vercel 필수"가 아니라면 이 경로가 운영 부담이 가장 적다.

---

## 6. 영상(WebRTC)은 별도 트랙

현재 영상은 `video_sources.json` + `signal_url` POST로 P2P 시그널링한다([dashboard.html](../monitor_server/web/dashboard.html)).
시그널링 메시지는 터널로 통과시킬 수 있어도 **실제 미디어는 P2P**라, 인터넷 너머 연결은
보통 **TURN 서버**가 필요하다. 1차 릴리스는 "상태·이벤트·지도·통계"만 외부로 열고,
영상은 후속(미디어 릴레이/TURN, 예: mediamtx)으로 분리할 것을 권장.

---

## 7. 롤아웃 단계

- **Phase 0 — 보안 하드닝**: §5 체크리스트(SECRET_KEY/비번/CORS) 먼저. 코드 거의 안 바뀜.
- **Phase 1 — 터널 노출**: 로컬에 `cloudflared` 설치 → `monitor.도메인.com → localhost:5000`.
  이 시점에서 이미 "외부에서 보기"는 완성(폴링 그대로).
- **Phase 2 — Vercel 프론트(선택)**: dashboard를 정적 SPA로 분리, `API_BASE`를 터널 URL로.
  크로스사이트 쿠키/CORS(§5-3,4) 처리. *동일출처 유지를 택하면 이 단계 생략 가능.*
- **Phase 3 — 동적 강화(선택)**: 폴링 → SSE 푸시 엔드포인트 추가.
- **Phase 4 — 영상(후속)**: TURN/미디어 릴레이.

---

## 8. 결정이 필요한 분기

1. **프론트 호스팅**: (a) Vercel로 분리 vs (b) Flask가 계속 서빙(터널만). — (b)가 운영 최소.
2. **터널 제품**: Cloudflare Tunnel(무료·도메인·Access) vs Tailscale Funnel vs ngrok.
3. **동적 수준**: 2초 폴링으로 충분한지, SSE 푸시까지 갈지.
4. **인증 강도**: 현 세션 로그인 유지 vs Cloudflare Access 추가.
