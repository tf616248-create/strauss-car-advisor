import EmployeeApp from './employee/EmployeeApp'
import RepScreen from './rep/RepScreen'

export default function App() {
  return window.location.pathname.startsWith('/rep') ? <RepScreen /> : <EmployeeApp />
}
