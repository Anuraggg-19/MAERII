import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "../../app/static/style.css";
import "./styles/migration.css";
import "./styles/assistant.css";

createRoot(document.getElementById("root")).render(<App />);
