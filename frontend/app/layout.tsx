import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google"; // taste-skill-ignore
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
});
// Shipping documents are fixed-width records; only they use this face.
const documentFace = JetBrains_Mono({ // taste-skill-ignore
  subsets: ["latin"],
  variable: "--font-document",
});

export const metadata: Metadata = {
  title: "CLEAR — Exception workspace",
  description:
    "Investigate shipment exceptions, assess supply exposure, and approve validated recovery plans.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${archivo.variable} ${documentFace.variable}`}>
      <body>{children}</body>
    </html>
  );
}
