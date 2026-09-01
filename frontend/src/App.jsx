import { useEffect, useState } from "react";
import { getJson } from "./api/client";

function App() {
  const [message, setMessage] = useState("Connecting to backend...");

  useEffect(() => {
    getJson("/api/test")
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