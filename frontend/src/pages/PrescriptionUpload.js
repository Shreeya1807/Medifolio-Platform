import React, { useState } from "react";

const PrescriptionUpload = () => {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState("");

  const uploadFile = async () => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("http://127.0.0.1:5000/api/upload-prescription", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    setResult(data.recognized_text);
  };

  return (
    <div>
      <h2>Upload Prescription</h2>
      <input type="file" onChange={(e) => setFile(e.target.files[0])} />
      <button onClick={uploadFile}>Upload</button>
      {result && (
        <div>
          <h4>Recognized Text:</h4>
          <p>{result}</p>
        </div>
      )}
    </div>
  );
};

export default PrescriptionUpload;
