import { useEffect, useState } from "react";

function App() {
  const [message, setMessage] = useState("Connecting to backend...");

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/test")
      .then((response) => response.json())
      .then((data) => {
        setMessage(data.message);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Could not connect to backend.");
      });
  }, []);

  return (
    <div>
      <h1>Adaptive Procurement Scheduling</h1>
      <p>{message}</p>
    </div>
  );
}

export default App;