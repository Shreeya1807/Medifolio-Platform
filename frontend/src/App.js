import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import PrescriptionUpload from "./pages/PrescriptionUpload";

const App = () => {
  return (
    <Router>
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
        <Navbar />
        <main style={{ flex: 1, padding: "20px" }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/upload" element={<PrescriptionUpload />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </Router>
  );
};

export default App;
