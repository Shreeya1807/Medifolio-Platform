import React, { useState } from "react";

const Chat = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const sendMessage = async () => {
    const response = await fetch("http://127.0.0.1:5000/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: input }),
    });
    const data = await response.json();
    console.log(data);
    setMessages([...messages, { user: input, bot: data.response }]);
    setInput("");
  };

  return (
    <div>
      <h2>Chat with Medical Consultant</h2>
      <div style={{ border: "1px solid #ccc", padding: "10px", height: "300px", overflowY: "scroll" }}>
        {messages.map((msg, idx) => (
          <div key={idx}>
            <p><strong>You:</strong> {msg.user}</p>
            <p><strong>Bot:</strong> {msg.bot}</p>
          </div>
        ))}
      </div>
      <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask something..." />
      <button onClick={sendMessage}>Send</button>
    </div>
  );
};

export default Chat;
