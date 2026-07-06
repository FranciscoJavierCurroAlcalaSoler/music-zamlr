import { useState, useEffect } from "react";
import { TrackTable } from "./components/TrackTable";

function App() {
  const [message, setMessage] = useState("loading...");

  useEffect(() => {
    fetch("http://localhost:8000/api/ping")
      .then((response) => response.json())
      .then((data) => setMessage(data.message))
      .catch(() => setMessage("could not reach backend"));
  }, []);

  return (
    <div>
      <TrackTable />
    </div>
  );
}

export default App;