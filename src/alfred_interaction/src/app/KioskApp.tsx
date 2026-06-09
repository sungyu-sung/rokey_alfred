import { useEffect } from 'react';
import { kioskConfig } from '@/config';
import { useIdleTimer, useKioskMode, useUiSounds } from '@/core/hooks';
import {
  robotStatusToEvent,
  useKioskDispatch,
  useKioskState,
  type RobotStatus,
} from '@/core/kiosk';
import { KioskRouter } from './KioskRouter';
import { StaffCallOverlay } from './StaffCallOverlay';
import styles from './App.module.css';

/**
 * Kiosk shell: applies kiosk-mode hardening, runs the idle→patrol timer on
 * interactive screens, and renders the current screen plus the staff overlay.
 */
export function KioskApp() {
  const { screen } = useKioskState();
  const dispatch = useKioskDispatch();

  useKioskMode({
    requestFullscreen: kioskConfig.requestFullscreen,
    hideCursor: kioskConfig.hideCursor,
  });

  // Short click sound on every button press (all screens).
  useUiSounds();

  const idleEnabled =
    screen === 'home' || screen === 'map' || screen === 'voice';

  useIdleTimer({
    timeoutMs: kioskConfig.idleTimeoutMs,
    enabled: idleEnabled,
    onIdle: () => dispatch({ type: 'IDLE_TIMEOUT' }),
  });

  // Manual test hook (no robot needed): drive any inbound robot status from the
  // console, e.g. window.alfredRobotStatus('DOCKING'). The collaborator's
  // ros_bridge subscription does the same: dispatch(robotStatusToEvent(status)).
  useEffect(() => {
    const w = window as unknown as {
      alfredRobotStatus?: (s: RobotStatus) => void;
    };
    w.alfredRobotStatus = (s) => {
      const event = robotStatusToEvent(s);
      if (event) dispatch(event);
    };
    console.info(
      "[robot-status] test: window.alfredRobotStatus('DOCKING'|'UNDOCKING'|'WAITING_1F'|'ESCORT_1F_FINISHED'|'ESCORT_COMPLETED'|'PATROL'|'FIRE'|'INJURED'|'SUSPICIOUS')",
    );
    return () => {
      delete w.alfredRobotStatus;
    };
  }, [dispatch]);

  return (
    <div className={styles.app}>
      <KioskRouter />
      <StaffCallOverlay />
    </div>
  );
}
