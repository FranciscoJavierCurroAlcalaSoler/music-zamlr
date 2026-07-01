import { useState, useEffect } from "react";

function App() {
  const [message, setMessage] = useState("loading...");

  useEffect(() => {
    fetch("http://localhost:8000/api/ping")
      .then((response) => response.json())
      .then((data) => setMessage(data.message))
      .catch(() => setMessage("could not reach backend"));
  }, []);

  return <h1>Backend says: {message}</h1>;
}

export default App;