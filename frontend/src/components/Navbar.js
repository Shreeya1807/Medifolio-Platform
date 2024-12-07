import React from "react";
import { Link } from "react-router-dom";

const Navbar = () => {
    return (
        <nav style={{ backgroundColor: "#007bff", padding: "10px" }}>
            <ul style={{ display: "flex", listStyle: "none", margin: 0, padding: 0 }}>
                <li style={{ marginRight: "10px" }}>
                    <Link to="/" style={{ color: "white", textDecoration: "none" }}>
                        Dashboard
                    </Link>
                </li>
                <li style={{ marginRight: "10px" }}>
                    <Link to="/chat" style={{ color: "white", textDecoration: "none" }}>
                        Chat
                    </Link>
                </li>
                <li>
                    <Link to="/upload" style={{ color: "white", textDecoration: "none" }}>
                        Upload Prescription
                    </Link>
                </li>
            </ul>
        </nav>
    );
};

export default Navbar;
