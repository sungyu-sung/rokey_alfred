import type { KioskEvent } from './types';

/**
 * Inbound robot state strings (IF-02) published by the robot over ros_bridge
 * (e.g. on `/robotN/escort_state`). The transport layer subscribes and feeds each
 * value to `robotStatusToEvent`, then dispatches the result to the kiosk.
 */
export type RobotStatus =
  | 'ESCORT_1F'
  | 'ESCORT_2F'
  | 'WAITING_1F'
  | 'WAITING_2F'
  | 'ESCORT_1F_FINISHED'
  | 'ESCORT_2F_FINISHED'
  | 'ESCORT_COMPLETED'
  | 'DOCKING'
  | 'UNDOCKING'
  | 'PATROL'
  | 'FIRE'
  | 'INJURED'
  | 'SUSPICIOUS';

/**
 * Map an inbound robot status → the kiosk event that shows the matching screen.
 * The collaborator's ros_bridge subscription does: `dispatch(robotStatusToEvent(s))`.
 *
 * Returns `null` for ESCORT_1F/2F: the on-screen escort (the `guiding` screen) is
 * created by the local guide flow because `START_GUIDING` carries a
 * `NavigationSession` (destination/progress) that the status string alone lacks.
 * Every other status maps to a screen here.
 */
export function robotStatusToEvent(status: RobotStatus): KioskEvent | null {
  switch (status) {
    case 'DOCKING':
    case 'UNDOCKING':
      return { type: 'ENTER_CHARGING' };

    case 'WAITING_1F':
    case 'WAITING_2F':
      return { type: 'ENTER_WAITING', info: { kind: 'waiting' } };

    // Done on this floor → send the user to the other floor (cross-floor handoff).
    case 'ESCORT_1F_FINISHED':
      return { type: 'ENTER_WAITING', info: { kind: 'transfer', toFloorId: 'F2' } };
    case 'ESCORT_2F_FINISHED':
      return { type: 'ENTER_WAITING', info: { kind: 'transfer', toFloorId: 'F1' } };

    case 'ESCORT_COMPLETED':
      return { type: 'END_GUIDING' }; // final arrival → back to patrol

    case 'PATROL':
      return { type: 'EXIT_ROBOT_SCREEN' };

    case 'FIRE':
    case 'INJURED':
    case 'SUSPICIOUS':
      return { type: 'DETECTION', detection: status };

    case 'ESCORT_1F':
    case 'ESCORT_2F':
      return null; // on-screen escort owns the guiding screen (needs a session)

    default:
      return null;
  }
}
