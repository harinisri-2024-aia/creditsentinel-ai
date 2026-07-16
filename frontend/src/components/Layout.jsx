import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Shield, LayoutDashboard, Cpu, Activity, LogOut, Menu, Users, GitCompare, UploadCloud, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export function PublicNav() {
  const navigate = useNavigate();
  return (
    <header className="fixed top-0 left-0 right-0 z-50 px-6 py-4">
      <div className="max-w-7xl mx-auto glass flex items-center justify-between px-6 py-3">
        <Link to="/" className="flex items-center gap-2 font-bold text-lg">
          <Shield className="text-accent" size={22} />
          Credit<span className="gradient-text">Sentinel</span>
        </Link>
        <nav className="hidden md:flex items-center gap-8 text-sm text-muted">
          <a href="#problem" className="hover:text-accent transition">Problem</a>
          <a href="#features" className="hover:text-accent transition">Features</a>
          <a href="#workflow" className="hover:text-accent transition">Workflow</a>
        </nav>
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/login")} className="btn-ghost text-sm py-2 px-4">
            Log in
          </button>
          <button onClick={() => navigate("/register")} className="btn-primary text-sm py-2 px-4">
            Get Started
          </button>
        </div>
      </div>
    </header>
  );
}

export function DashboardLayout({ children }) {
  const { user, logout, hasRole } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const links = [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/models", label: "Models", icon: Cpu },
    { to: "/applicants", label: "Applicants", icon: Users },
    { to: "/compare", label: "Compare", icon: GitCompare },
    { to: "/upload", label: "Upload Dataset", icon: UploadCloud, roles: ["data_scientist"] },
    { to: "/monitoring", label: "Monitoring", icon: Activity },
    { to: "/admin", label: "Admin", icon: ShieldCheck, roles: ["admin"] },
  ].filter((link) => !link.roles || hasRole(...link.roles));

  return (
    <div className="min-h-screen flex bg-bg">
      <aside className="w-64 hidden md:flex flex-col glass m-4 mr-0 rounded-r-none p-5">
        <Link to="/" className="flex items-center gap-2 font-bold text-lg mb-10">
          <Shield className="text-accent" size={22} />
          Credit<span className="gradient-text">Sentinel</span>
        </Link>
        <nav className="flex flex-col gap-1 flex-1 overflow-y-auto">
          {links.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition ${
                  active
                    ? "bg-accent/10 text-accent border border-accent/30"
                    : "text-muted hover:text-white hover:bg-white/5"
                }`}
              >
                <Icon size={18} /> {label}
              </Link>
            );
          })}
        </nav>
        <div className="pt-4 border-t border-white/10">
          <p className="text-sm font-medium">{user?.full_name}</p>
          <p className="text-xs text-muted mb-1">{user?.email}</p>
          {user?.role && (
            <span className="inline-block text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-accent/10 text-accent mb-3">
              {user.role.replaceAll("_", " ")}
            </span>
          )}
          <button
            onClick={() => {
              logout();
              navigate("/");
            }}
            className="flex items-center gap-2 text-sm text-muted hover:text-red-400 transition"
          >
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="md:hidden flex items-center justify-between p-4 glass m-4 mb-0">
          <span className="font-bold flex items-center gap-2">
            <Shield className="text-accent" size={20} /> CreditSentinel
          </span>
          <Menu />
        </header>
        <main className="flex-1 p-4 md:p-8 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
