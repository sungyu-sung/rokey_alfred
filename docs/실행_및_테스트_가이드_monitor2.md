# monitor2 실행 · 테스트 가이드

monitor2 = `monitor`(클라우드/대시보드 작업) + `develop` robot-side 통합 브랜치.
ROS2 수집(LAN) → Supabase(클라우드) → Vercel(외부 조회) 경로의 실행·검증 방법.

```
로봇 --DDS--> robot_state_publisher_node --/robotN/robot_state--> 펌프(main.py,supabase)
              (amcl_pose+battery → RobotState)                         │ HTTPS(아웃바운드)
                                                                       ▼
                                                                  Supabase Postgres
외부 브라우저 --- Vercel(web-vercel) --- supabase-js (로그인 후 읽기) ----┘
```

> ⚠ DDS는 LAN 전용 → 펌프 PC는 로봇과 같은 와이파이 + 같은 `ROS_DOMAIN_ID`.
> 외부 시청자는 아무 망에서나 Vercel URL 접속(로봇 망 무관).
> 영상(WebRTC)은 별도 트랙(외부는 TURN 서버 필요) — 이 가이드 범위 밖.

---

## 0. 사전 준비 (1회성)

1. **Supabase 프로젝트** 생성 → SQL Editor에서 순서대로 실행:
   `supabase/01_schema.sql` → `02_functions.sql` → `03_grants.sql`
   → Authentication > Users 에 관제 계정(이메일+비번) 추가
2. **`.env`** (`monitor_server/.env`, `.env.example` 복사):
   ```
   FMS_BACKEND=supabase
   SUPABASE_URL=https://<프로젝트ref>.supabase.co
   SUPABASE_SERVICE_KEY=<service_role 키>   # 이 PC에만, 브라우저로 절대 X
   FMS_STATUS_TIMEOUT=10.0
   ```
3. **Vercel**: `monitor_server/web-vercel/` 정적 배포 + `supabase-config.js`의 `url`/`anonKey` 채움
4. **빌드**:
   ```bash
   cd ~/alfred_ws
   git checkout monitor2
   source /opt/ros/humble/setup.bash
   colcon build --packages-select alfred_interfaces alfred_bridge alfred_vision alfred_driving --symlink-install
   source install/setup.bash
   ```

---

## 1. 실행 (로봇 LAN PC)

세 개의 터미널, 모두 같은 환경 소싱:
```bash
cd ~/alfred_ws
source /opt/ros/humble/setup.bash && source install/setup.bash
export ROS_DOMAIN_ID=2          # 로봇과 동일하게
```

**터미널 1 — robot_state 생성** (실로봇 amcl_pose/battery가 흐르는 상태):
```bash
ros2 run alfred_bridge robot_state_publisher_node
# amcl_pose + battery_state → /robot2/robot_state, /robot4/robot_state (1Hz)
```

**터미널 2 — 펌프 (ROS2 → Supabase)**:
```bash
cd monitor_server
set -a; source .env; set +a            # FMS_BACKEND=supabase
python3 main.py
# 로그에 "monitor server ready - ROS2 ingest -> Supabase (no local API)" → 정상
# 이 모드는 Flask(5000)를 띄우지 않음(write-only 펌프)
```

**터미널 3 (선택) — 로컬 관제 대시보드** (localhost:5000, 이벤트는 Supabase 공유):
```bash
cd monitor_server
set -a; source .env; set +a
FMS_BACKEND=sqlite python3 main.py     # sqlite 모드여야 Flask가 뜸
```

---

## 2. 테스트 절차

### 2-1. Supabase 연결/인증 (쓰기 없음)
```bash
cd monitor_server; set -a; source .env; set +a
python3 - <<'PY'
import store
sb = store.SupabaseStore(); sb.init()
for r in ("robot2","robot4"):
    print(r, sb.get_prev_status(r))
print("OK: 연결/인증/RLS우회/테이블 정상")
PY
```

### 2-2. 적재 코드경로 (in-process) — ROS 없이 펌프 쓰기 경로 검증
> 샌드박스/CI 등 **프로세스 간 DDS 디스커버리가 막힌 환경**에서 적재만 따로 확인할 때.
> (ROS 전송 계층은 실로봇/같은 LAN에서 검증)
```bash
cd monitor_server; set -a; source .env; set +a
python3 - <<'PY'
import store, robot_registry
store.init()
reg = robot_registry.RobotRegistry()
reg.update_from_status({"robot_id":"robot2","state":"INTERACTING",
    "pose":{"x":9.99,"y":9.99,"theta":1.57},"battery":42,
    "current_task_id":"SIMTEST","task_status":"RUNNING","error_code":"","timestamp":""})
sb = store.SupabaseStore(); sb.init()
print("latest:", sb._request("GET","/latest_robot_status?robot_id=eq.robot2&select=state,battery,x,y,last_seen")[0])
print("log:", sb._request("GET","/robot_status_log?robot_id=eq.robot2&select=id,state,prev_state&order=id.desc&limit=1"))
PY
```
기대: `latest`가 INTERACTING/42/9.99로 갱신 + `log`에 새 행(prev_state=PATROL).
**테스트 후 원복**(아래 정리 스니펫) 필수.

### 2-3. ROS 토픽 → 적재 (실로봇 또는 같은 LAN 시뮬레이터)
터미널 1·2 실행 상태에서, 다른 터미널:
```bash
ros2 topic echo --once /robot2/robot_state        # robot_state가 실제로 흐르는지
```
→ Supabase Table Editor에서 `latest_robot_status` 행이 갱신되는지 확인.
> ⚠ 한 PC 안 두 프로세스가 서로 못 보면 DDS 멀티캐스트 차단 환경 → 2-2로 대체.

### 2-4. 다른 LAN 조회 (외부 동작 확인)
폰을 **LTE/다른 와이파이**로 → **Vercel 배포 URL** 접속 → 로그인 →
로봇 상태/위치가 보이고 갱신되면 성공. (로컬 PC가 그 망에 없어도 됨)

---

## 3. 테스트 데이터 정리 (2-2 실행 후)
```bash
cd monitor_server; set -a; source .env; set +a
python3 - <<'PY'
import store
sb = store.SupabaseStore(); sb.init()
sb._request("DELETE","/robot_status_log?task_id=eq.SIMTEST", prefer="return=minimal")
sb._request("PATCH","/latest_robot_status?robot_id=eq.robot2",
    body={"state":"PATROL","battery":-1,"x":0,"y":0,"theta":None,
          "current_task_id":None,"task_status":None,"error_code":None},
    prefer="return=minimal")
print("정리 완료")
PY
```

---

## 4. 검증 현황 (2026-06-09 기준, 이 환경)

| 항목 | 상태 |
|---|---|
| monitor2 빌드(4 패키지) | ✅ |
| Supabase 연결/인증/테이블 | ✅ |
| 적재 코드경로(robot_registry→store→Supabase, 변화감지 로그 포함) | ✅ (2-2로 확인) |
| ROS 전송 계층(`/robot_state` 수신) | develop 실로봇에서 검증(동일 코드) — 이 샌드박스는 프로세스간 DDS 차단으로 미실행 |
| 영상(WebRTC) 외부 | 미포함(TURN 필요) |
