import type { Metadata } from "next";
import "./styles.css";
import { AppSidebar } from "../components/app-sidebar";

export const metadata: Metadata = {
  title: "ARKANA | Market Data",
  description: "ARKANA trading intelligence market-data foundation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id"><body><div className="app-shell"><AppSidebar /><main>{children}</main></div></body></html>;
}
