// TEMPORARY - for testing only. The codes shown on the login screens, so testers can get in.
// They must match backend/.env (EMPLOYEE_CODES, REP_PASSCODE). To remove before the pilot:
// delete this file and testCodes.test.jsx, and the <TestCodesNote> in Login.jsx and RepScreen.jsx.

export const TEST_EMPLOYEE_CODES = '1111, 2222, 3333 … 9999'
export const TEST_REP_PASSCODE = '2222'

export function TestCodesNote({ children }) {
  return (
    <p className="test-codes" role="note" aria-label="קודים לבדיקות">
      <strong>לבדיקות בלבד:</strong> {children}
      <span className="test-codes__later">הקודים יימחקו לפני השימוש האמיתי.</span>
    </p>
  )
}
