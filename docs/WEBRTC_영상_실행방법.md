# WebRTC 로봇 카메라 영상 — 실행 방법

monitor 대시보드 "영상(WebRTC)" 탭에서 로봇 카메라를 실시간으로 본다.
구조: **로봇 카메라(OAK-D compressed) → `video_sender_node`(aiortc) → 브라우저 P2P**.
대시보드/서버는 미디어를 중계하지 않고 시그널링 URL(`video_sources.json`)만 제공한다.

> 검증 완료(2026-06-09): robot2 실시간 영상 OK. robot4는 카메라 RGB가 0.1Hz로만
> 발행돼 영상 안 나옴 — robot4 OAK-D RGB를 정상 fps로 켜야 함(robot4-side).

---

## 0. 환경 (모든 터미널 공통)

```bash
cd ~/alfred_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=2
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp     # 보통 .bashrc에 이미 있음
```
- 이 두 환경변수가 안 맞으면 로봇 토픽이 아예 안 보인다(조용히 0건).
- WebRTC 의존성(센더 돌릴 머신에 1회): `pip install aiortc aiohttp opencv-python numpy`

---

## 1. 대시보드(monitor 서버) 실행

⚠️ **`FMS_BACKEND=sqlite`로 띄워야** 영상 탭이 있는 :5000 로컬 대시보드가 뜬다(supabase면 펌프만, 로컬 API 없음).
⚠️ **단, `.env`(SUPABASE_URL/KEY)도 함께 로드해야** 이벤트가 Supabase 단일 소스로 공유된다.
`SUPABASE_URL`이 없으면 로컬 대시보드가 자기 sqlite 이벤트로 폴백 → Vercel과 조치(resolve)가 따로 논다.

```bash
cd ~/alfred_ws/monitor_server
set -a; source .env; set +a              # SUPABASE_URL/KEY 로드 (이벤트 Supabase 공유)
FMS_BACKEND=sqlite python3 main.py       # 인라인 override → 로컬 :5000 유지, 상태는 sqlite
#   http://<이 머신 IP>:5000 (예: http://192.168.107.77:5000)
```

- `supabase` 모드 = ROS2 → Supabase 펌프(로컬 대시보드 X). Vercel 공개 대시보드는 로봇
  사설 IP의 WebRTC 센더에 직접 접속 불가 → **로컬 영상은 sqlite 모드에서** 본다.

## 2. 영상 센더 실행 (로봇별 1개, 포트 다르게)

> 센더는 **카메라가 달린 로봇이 아니어도**, ROS 토픽을 받을 수 있는 머신이면 어디서든 OK.
> 단 `video_sources.json`의 signal_url IP/포트가 **센더 띄운 머신**과 같아야 한다.
> `ros2 run`은 빌드된 옛 코드라, 수정본은 `python3 src/...`로 실행한다.

```bash
# robot2 (포트 8081)
python3 src/alfred_vision/alfred_vision/video_sender_node.py --ros-args \
  -p image_topic:=/robot2/oakd/rgb/image_raw/compressed -p http_port:=8081

# robot4 (새 터미널, 포트 8082) — 동시 송출
python3 src/alfred_vision/alfred_vision/video_sender_node.py --ros-args \
  -p image_topic:=/robot4/oakd/rgb/image_raw/compressed -p http_port:=8082
```

각 센더 터미널에 3초마다 진단 로그가 뜬다:
```
[진단] 최근 3초 28프레임 (누적 ...) · ...1920x1080 OK   ← 정상(프레임 수신 중)
[진단] 최근 3초 0프레임  (누적 0)  · (아직 수신 없음)     ← 카메라가 안 흐름
```

## 3. 시그널링 설정 (`monitor_server/web/video_sources.json`)

현재 값(테스트: 센더를 .77에서 돌린 구성):
```json
{ "robot_id": "robot2", "signal_url": "http://192.168.107.77:8081/offer" }
{ "robot_id": "robot4", "signal_url": "http://192.168.107.77:8082/offer" }
```
- **production**(각 로봇이 자기 카메라 송출): 센더를 로봇에서 돌리고
  robot2→`http://192.168.107.102:8081/offer`, robot4→`http://192.168.107.104:8081/offer`로.

## 4. 접속·연결

1. 브라우저 `http://<대시보드 IP>:5000` 로그인(admin/admin1234)
2. **영상(WebRTC)** 탭 (이미 열려 있었으면 F5)
3. 각 카드 **[연결]** → "연결됨" + 영상

---

## 5. 종료

```bash
# 센더: 각 터미널에서 Ctrl+C
# 대시보드/센더 포트로 일괄 종료:
for p in 5000 8081 8082; do
  pid=$(ss -tlnp | grep ":$p " | grep -oP 'pid=\K[0-9]+' | head -1)
  [ -n "$pid" ] && kill "$pid"
done
```

---

## 빠른 점검 (영상 안 나올 때)

```bash
# 1) 카메라가 실제로 흐르나? (Hz 10 정도면 정상, 0/끊김이면 로봇 카메라 문제)
ros2 topic hz /robot2/oakd/rgb/image_raw/compressed

# 2) 센더 살아있나
curl http://192.168.107.77:8081/health      # {"status":"ok","peers":N}

# 3) 센더 진단 로그가 0프레임이면 → DDS/카메라 문제, N프레임이면 → 정상
```

- **"연결됨"인데 검은/멈춤 화면** → 센더가 프레임을 못 받는 것(진단 로그 0). 카메라 Hz 확인.
- **"실패"** → 그 IP:포트에 센더가 없거나 방화벽/주소 불일치.
- **robot4 0.1Hz 문제** → robot4 OAK-D RGB 스트림을 정상 fps로 켜야 함(robot4 카메라 담당).

> 머신/층 매핑 등 환경 사실은 메모리(`webrtc-video-deployment`, `robot-floor-mapping-반대`) 참고.
