import EmployeeScreen from './employee/EmployeeScreen'
import RepScreen from './rep/RepScreen'

export default function App() {
  return window.location.pathname.startsWith('/rep') ? <RepScreen /> : <EmployeeScreen />
}
