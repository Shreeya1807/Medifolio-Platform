import React, { useState, useEffect } from "react";

const Dashboard = () => {
  const [patient, setPatient] = useState(null);
  const [doctors, setDoctors] = useState([]);

  useEffect(() => {
    // Fetch patient data
    fetch("http://127.0.0.1:5000/api/patient/123")
      .then((res) => res.json())
      .then((data) => setPatient(data));

    // Fetch doctors
    fetch("http://127.0.0.1:5000/api/doctors")
      .then((res) => res.json())
      .then((data) => setDoctors(data));
  }, []);

  return (
    <div>
      <h2>Patient Dashboard</h2>
      {patient && (
        <div>
          <h4>Patient Info</h4>
          <p><strong>Name:</strong> {patient.name}</p>
          <p><strong>History:</strong> {patient.history.join(", ")}</p>
        </div>
      )}
      <h4>Recommended Doctors</h4>
      <ul>
        {doctors.map((doc, idx) => (
          <li key={idx}>
            <p><strong>Name:</strong> {doc.name}</p>
            <p><strong>Specialty:</strong> {doc.specialty}</p>
            <p><strong>Rating:</strong> {doc.rating}</p>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default Dashboard;
