import { useEffect, useRef } from 'react';
import { RobotFace, ScreenFrame } from '@/components';
import { useStrings } from '@/config';
import { useSpeak } from '@/services';
import styles from './ChargingScreen.module.css';

/**
 * Robot is docked / charging (IF-02 DOCKING / UNDOCKING). A calm full-screen face
 * so passers-by see the robot is just charging, not out of order. UNDOCKING reuses
 * this screen briefly before the robot reports PATROL. In VI mode it's spoken once.
 */
export function ChargingScreen() {
  const strings = useStrings();
  const speak = useSpeak();
  const announcedRef = useRef(false);

  useEffect(() => {
    if (announcedRef.current) return;
    announcedRef.current = true;
    speak(strings.charging.caption);
  }, [speak, strings]);

  return (
    <ScreenFrame tone="dark">
      <div className={styles.body}>
        <RobotFace
          caption={strings.charging.caption}
          subtitle={strings.charging.subtitle}
        />
      </div>
    </ScreenFrame>
  );
}
