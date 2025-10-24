"use client";

import { useEffect } from "react";
import { logout } from "@/api/api-client";

export default function LogoutPage() {
  useEffect(() => {
    logout();
  }, []);

  return <p>Closing session...</p>;
}
