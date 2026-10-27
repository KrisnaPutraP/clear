import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CLEAR — Exception workspace",
  description:
    "Investigate shipment exceptions, assess supply exposure, and approve validated recovery plans.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
