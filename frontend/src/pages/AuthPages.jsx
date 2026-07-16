import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { Input, Button, Card } from "../components/UI";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center px-6">
      <Card className="w-full max-w-md" hover={false}>
        <Link to="/" className="flex items-center gap-2 font-bold text-lg mb-8 justify-center">
          <Shield className="text-accent" size={22} />
          Credit<span className="gradient-text">Sentinel</span>
        </Link>
        <h1 className="text-2xl font-bold mb-1 text-center">Welcome back</h1>
        <p className="text-muted text-sm text-center mb-8">Log in to your governance workspace</p>
        {error && <p className="text-red-400 text-sm mb-4 text-center">{error}</p>}
        <form onSubmit={handleSubmit}>
          <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="you@company.com" />
          <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••" />
          <Button type="submit" className="w-full mt-2" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </form>
        <p className="text-muted text-sm text-center mt-6">
          Don't have an account? <Link to="/register" className="text-accent">Create one</Link>
        </p>
      </Card>
    </div>
  );
}

export function RegisterPage() {
  const [form, setForm] = useState({ full_name: "", email: "", company: "", password: "", role: "data_scientist" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const validate = () => {
    const fullName = form.full_name.trim();
    const email = form.email.trim();
    if (fullName.length < 2) return "Please enter your full name.";
    if (!email.includes("@") || !email.includes(".")) return "Please enter a valid email address.";
    if (form.password.length < 8) return "Password must be at least 8 characters.";
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setLoading(true);
    try {
      await register({
        ...form,
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        company: form.company.trim(),
      });
      navigate("/dashboard");
    } catch (err) {
      setError(err?.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center px-6">
      <Card className="w-full max-w-md" hover={false}>
        <Link to="/" className="flex items-center gap-2 font-bold text-lg mb-8 justify-center">
          <Shield className="text-accent" size={22} />
          Credit<span className="gradient-text">Sentinel</span>
        </Link>
        <h1 className="text-2xl font-bold mb-1 text-center">Create your workspace</h1>
        <p className="text-muted text-sm text-center mb-8">Start governing your credit risk models</p>
        {error && <p className="text-red-400 text-sm mb-4 text-center">{error}</p>}
        <form onSubmit={handleSubmit}>
          <Input label="Full name" value={form.full_name} onChange={update("full_name")} required minLength={2} placeholder="Jane Doe" />
          <Input label="Email" type="email" value={form.email} onChange={update("email")} required placeholder="you@company.com" />
          <Input label="Company" value={form.company} onChange={update("company")} placeholder="Acme Lending Co." />
          <Input label="Password" type="password" value={form.password} onChange={update("password")} required minLength={8} placeholder="•••••••• (min 8 characters)" />
          <div className="mb-4">
            <label className="block text-sm text-muted mb-1.5">Role</label>
            <select className="input-field" value={form.role} onChange={update("role")}>
              <option value="data_scientist">Data Scientist — train models, upload datasets</option>
              <option value="auditor">Auditor — view fairness reports &amp; logs</option>
              <option value="loan_officer">Loan Officer — view applicants &amp; predictions</option>
              <option value="admin">Admin — manage users, approve deployment</option>
            </select>
          </div>
          <Button type="submit" className="w-full mt-2" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
          </Button>
        </form>
        <p className="text-muted text-sm text-center mt-6">
          Already have an account? <Link to="/login" className="text-accent">Log in</Link>
        </p>
      </Card>
    </div>
  );
}
