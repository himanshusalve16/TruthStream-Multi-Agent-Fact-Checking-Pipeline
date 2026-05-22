import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import JobPage from './pages/JobPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import { JobProvider } from './context/JobContext'

function App() {
  return (
    <BrowserRouter>
      <JobProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/jobs/:id" element={<JobPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </JobProvider>
    </BrowserRouter>
  )
}

export default App
