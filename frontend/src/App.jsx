import EmployeeApp from './employee/EmployeeApp'
import RepScreen from './rep/RepScreen'
import AccessibilityStatement from './components/AccessibilityStatement'

export default function App() {
  const path = window.location.pathname
  if (path.startsWith('/accessibility')) return <AccessibilityStatement />
  return path.startsWith('/rep') ? <RepScreen /> : <EmployeeApp />
}
