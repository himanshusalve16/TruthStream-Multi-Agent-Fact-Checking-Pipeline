import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import JobPage from './pages/JobPage'
import HistoryPage from './pages/HistoryPage'

import { JobProvider } from './context/JobContext'

function App() {
  return (
    <BrowserRouter>
      <JobProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/jobs/:id" element={<JobPage />} />
          <Route path="/history" element={<HistoryPage />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </JobProvider>
    </BrowserRouter>
  )
}

export default App
