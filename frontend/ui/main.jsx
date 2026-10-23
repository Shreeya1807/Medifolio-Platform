import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { io } from "socket.io-client";
import "./style.css";
let csrf = "";
async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await r.json();
  if (!r.ok) throw Error(d.error || "Request failed");
  return d;
}
function App() {
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState("Records"),
    [patients, setPatients] = useState([]),
    [patient, setPatient] = useState(""),
    [records, setRecords] = useState([]),
    [selected, setSelected] = useState(null),
    [title, setTitle] = useState(""),
    [text, setText] = useState(""),
    [doctors, setDoctors] = useState([]),
    [grants, setGrants] = useState([]),
    [events, setEvents] = useState([]),
    [appointments, setAppointments] = useState([]),
    [doctor, setDoctor] = useState(""),
    [scheduled, setScheduled] = useState(""),
    [call, setCall] = useState(null);
  const act = (fn) => async (e) => {
    e?.preventDefault();
    setError("");
    setBusy(true);
    try {
      await fn(e);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    api("/session")
      .then((d) => {
        csrf = d.csrf;
        setUser(d.user);
        setReady(true);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (user) {
      Promise.all([api("/patients"), api("/doctors"), api("/appointments")])
        .then(([p, d, a]) => {
          setPatients(p.patients);
          setPatient(p.patients[0]?.id || "");
          setDoctors(d.doctors);
          setDoctor(d.doctors[0]?.id || "");
          setAppointments(a.appointments);
        })
        .catch((e) => setError(e.message));
    }
  }, [user]);
  useEffect(() => {
    if (patient) {
      setSelected(null);
      setTitle("");
      setText("");
      api(`/patients/${patient}/records`)
        .then((d) => setRecords(d.records))
        .catch((e) => setError(e.message));
      if (user?.role === "patient")
        Promise.all([
          api(`/patients/${patient}/grants`),
          api(`/patients/${patient}/audit`),
        ])
          .then(([g, a]) => {
            setGrants(g.doctors);
            setEvents(a.events);
          })
          .catch((e) => setError(e.message));
    }
  }, [patient, user, tab]);
  async function open(id) {
    const d = await api("/records/" + id);
    setSelected(d);
    setTitle(d.versions[0].title);
    setText(d.versions[0].text);
  }
  async function save() {
    if (selected) {
      await api("/records/" + selected.id, "POST", {
        title,
        text,
        expected_version: selected.versions[0].version,
      });
      await open(selected.id);
    } else {
      await api(`/patients/${patient}/records`, "POST", { title, text });
      setTitle("");
      setText("");
    }
    setRecords((await api(`/patients/${patient}/records`)).records);
  }
  async function extract(file) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) throw Error("Choose a file under 5 MB");
    if (file.type === "text/plain") {
      setText((await file.text()).slice(0, 24000));
      return;
    }
    if (!["image/png", "image/jpeg"].includes(file.type))
      throw Error(
        "Import TXT, PNG or JPEG. Export PDF text or a page image first.",
      );
    const { createWorker } = await import("tesseract.js");
    const worker = await createWorker("eng");
    try {
      const result = await worker.recognize(file);
      setText(result.data.text.slice(0, 24000));
      setError(
        "Text recognized from the image. Review every detail before saving.",
      );
    } finally {
      await worker.terminate();
    }
  }
  if (!ready) return <p className="loading">Opening your workspace…{error}</p>;
  return (
    <>
      <header>
        <strong>
          ✚ medifolio<span>.</span>
        </strong>
        <span>Your care, connected.</span>
        {user && (
          <button
            className="quiet"
            onClick={act(async () => {
              await api("/logout", "POST", {});
              location.reload();
            })}
          >
            Sign out
          </button>
        )}
      </header>
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
      {!user ? (
        <main className="login">
          <div>
            <p className="eyebrow">A CLEARER PICTURE OF YOUR CARE</p>
            <h1>
              Your health story.
              <br />
              All in one place.
            </h1>
            <p>
              Keep records organized, choose who can access them, and connect
              with your care team.
            </p>
            <div className="notice">
              Portfolio demonstration. Use synthetic records only. This
              application does not diagnose conditions or recommend treatment.
            </div>
          </div>
          <form
            onSubmit={act(async (e) => {
              const f = new FormData(e.target);
              const d = await api("/login", "POST", Object.fromEntries(f));
              csrf = d.csrf;
              setUser(d.user);
            })}
          >
            <h2>Welcome back</h2>
            <p>
              Sign in with an account provisioned by your workspace operator.
            </p>
            <label>
              Username
              <input name="username" autoComplete="username" required />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            <button disabled={busy}>Open workspace</button>
          </form>
        </main>
      ) : (
        <div className="layout">
          <aside>
            <p className="eyebrow">YOUR WORKSPACE</p>
            {["Records", "Care team", "Consultations", "Access history"]
              .filter(
                (t) =>
                  user.role === "patient" ||
                  !["Care team", "Access history"].includes(t),
              )
              .map((t) => (
                <button
                  key={t}
                  className={tab === t ? "active" : "quiet"}
                  onClick={() => setTab(t)}
                >
                  {t}
                </button>
              ))}
            <div className="profile">
              <strong>{user.name}</strong>
              <p>{user.role} workspace</p>
            </div>
          </aside>
          <main className="content">
            <p className="eyebrow">PERSONAL HEALTH PORTFOLIO</p>
            <h1>
              {tab === "Records" ? "A little clarity. Better continuity." : tab}
            </h1>
            <p className="muted">
              Records are private by default. You control sharing with your care
              team.
            </p>
            {user.role === "doctor" && (
              <label>
                Shared patient
                <select
                  value={patient}
                  onChange={(e) => setPatient(e.target.value)}
                >
                  {patients.map((p) => (
                    <option value={p.id} key={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {tab === "Records" && (
              <>
                <div className="stats">
                  <article>
                    <strong>{records.length}</strong>
                    <span>Records in your portfolio</span>
                  </article>
                  <article>
                    <strong>Versioned</strong>
                    <span>Changes preserve earlier entries</span>
                  </article>
                  <article>
                    <strong>Private</strong>
                    <span>Access is checked and logged</span>
                  </article>
                </div>
                <div className="record-grid">
                  <section className="card">
                    <h2>Record timeline</h2>
                    {!records.length && (
                      <p>No records yet. Add a synthetic sample to explore.</p>
                    )}
                    {records.map((r) => (
                      <button
                        className="record"
                        key={r.id}
                        onClick={act(() => open(r.id))}
                      >
                        <strong>{r.title}</strong>
                        <span>
                          Version {r.version} ·{" "}
                          {new Date(r.created).toLocaleDateString()}
                        </span>
                      </button>
                    ))}
                    {user.role === "patient" && (
                      <button
                        className="quiet"
                        onClick={() => {
                          setSelected(null);
                          setTitle("");
                          setText("");
                        }}
                      >
                        ＋ New record
                      </button>
                    )}
                  </section>
                  <section className="card">
                    <h2>{selected ? "Record details" : "Add a record"}</h2>
                    {user.role === "patient" ? (
                      <form onSubmit={act(save)}>
                        <label>
                          Record title
                          <input
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            maxLength={120}
                            required
                          />
                        </label>
                        <label>
                          Record text
                          <textarea
                            aria-label="Record text"
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            maxLength={24000}
                            rows={9}
                            required
                          />
                        </label>
                        <label className="upload">
                          Import text or recognize an image
                          <input
                            type="file"
                            accept=".txt,.png,.jpg,.jpeg"
                            onChange={act((e) => extract(e.target.files[0]))}
                          />
                        </label>
                        <small>
                          Image OCR runs in your browser. Review extracted text
                          before saving. English language assets require
                          internet access.
                        </small>
                        <div className="actions">
                          <button disabled={busy || !patient}>
                            {busy
                              ? "Working…"
                              : selected
                                ? "Save new version"
                                : "Save record"}
                          </button>
                          <button
                            type="button"
                            className="quiet"
                            onClick={() => {
                              setTitle("Visit summary · sample");
                              setText(
                                "Synthetic example only. Visit date: 2026-10-22. Follow-up requested. Allergy history reviewed. No treatment recommendation is included.",
                              );
                            }}
                          >
                            Use sample
                          </button>
                        </div>
                      </form>
                    ) : (
                      <p className="record-text">
                        {text || "Select a shared record to view its contents."}
                      </p>
                    )}
                    {selected && (
                      <>
                        <h3>Search aids</h3>
                        <p>
                          {selected.versions[0].index.keywords.join(" · ") ||
                            "No indexed terms"}
                        </p>
                        <small>{selected.versions[0].index.notice}</small>
                        <h3>Version history</h3>
                        {selected.versions.map((v) => (
                          <details key={v.version}>
                            <summary>
                              Version {v.version} · {v.author}
                            </summary>
                            <p className="record-text">{v.text}</p>
                          </details>
                        ))}
                      </>
                    )}
                  </section>
                </div>
              </>
            )}
            {tab === "Care team" && (
              <section className="card">
                <h2>You decide who sees your records.</h2>
                <p>
                  Sharing lets a doctor read your current and previous record
                  versions. Revoking access prevents subsequent record requests
                  and consultation signaling.
                </p>
                {doctors.map((d) => (
                  <div className="team" key={d.id}>
                    <div>
                      <strong>{d.name}</strong>
                      <p>
                        {grants.includes(d.id) ? "Access granted" : "No access"}
                      </p>
                    </div>
                    <button
                      disabled={busy}
                      onClick={act(async () => {
                        const r = await api(
                          `/patients/${patient}/grants`,
                          grants.includes(d.id) ? "DELETE" : "POST",
                          { doctor: d.id },
                        );
                        setGrants(r.doctors);
                      })}
                    >
                      {grants.includes(d.id) ? "Revoke access" : "Grant access"}
                    </button>
                  </div>
                ))}
              </section>
            )}
            {tab === "Access history" && (
              <section className="card">
                <h2>A record of record access.</h2>
                <p>
                  Latest 200 events. Entries are append-only; a hash chain
                  supports integrity checks.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Actor</th>
                      <th>When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((e, i) => (
                      <tr key={i}>
                        <td>{e.action.replaceAll("_", " ")}</td>
                        <td>{e.actor}</td>
                        <td>{new Date(e.created).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
            {tab === "Consultations" && (
              <section className="card">
                <h2>Connect with your care team.</h2>
                {user.role === "patient" && (
                  <form
                    className="schedule"
                    onSubmit={act(async () => {
                      const r = await api("/appointments", "POST", {
                        doctor,
                        scheduled: new Date(scheduled).toISOString(),
                      });
                      setAppointments(r.appointments);
                    })}
                  >
                    <label>
                      Doctor
                      <select
                        value={doctor}
                        onChange={(e) => setDoctor(e.target.value)}
                      >
                        {doctors.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Local date and time
                      <input
                        type="datetime-local"
                        step="1800"
                        value={scheduled}
                        onChange={(e) => setScheduled(e.target.value)}
                        required
                      />
                    </label>
                    <button disabled={busy}>Schedule consultation</button>
                  </form>
                )}
                <p className="muted">
                  Share access first. Select a half-hour slot within 90 days.
                  Video requires camera permission; restrictive networks may
                  require TURN.
                </p>
                {appointments.map((a) => (
                  <div className="team" key={a.id}>
                    <div>
                      <strong>{new Date(a.scheduled).toLocaleString()}</strong>
                      <p>
                        {a.patient} ↔ {a.doctor}
                      </p>
                    </div>
                    <button onClick={() => setCall(a.id)}>
                      Join consultation
                    </button>
                  </div>
                ))}
                {call && (
                  <Video
                    appointment={call}
                    user={user}
                    onClose={() => setCall(null)}
                    onError={setError}
                  />
                )}
              </section>
            )}
          </main>
        </div>
      )}
      <footer>
        Synthetic demonstration workspace · No emergency or diagnostic services
      </footer>
    </>
  );
}
function Video({ appointment, user, onClose, onError }) {
  const local = useRef(),
    remote = useRef();
  const [state, setState] = useState("Preparing camera…");
  useEffect(() => {
    let disposed = false,
      stream,
      connection,
      socket,
      initiator = false,
      pending = [];
    async function offer() {
      if (connection.signalingState === "have-local-offer") {
        socket.emit("signal", {
          appointment,
          signal: { description: connection.localDescription },
        });
        return;
      }
      if (connection.signalingState !== "stable") return;
      await connection.setLocalDescription(await connection.createOffer());
      socket.emit("signal", {
        appointment,
        signal: { description: connection.localDescription },
      });
    }
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });
        if (disposed) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        local.current.srcObject = stream;
        const config = await api("/media-config");
        connection = new RTCPeerConnection(config);
        stream.getTracks().forEach((t) => connection.addTrack(t, stream));
        connection.ontrack = (e) => (remote.current.srcObject = e.streams[0]);
        connection.onconnectionstatechange = () =>
          setState("Connection: " + connection.connectionState);
        socket = io({ auth: { csrf }, transports: ["websocket"] });
        connection.onicecandidate = (e) => {
          if (e.candidate)
            socket.emit("signal", {
              appointment,
              signal: { candidate: e.candidate },
            });
        };
        socket.on("connect", () =>
          socket.emit("join_consultation", { appointment }, (d) => {
            if (!d.ok) return onError("Consultation unavailable");
            initiator = d.initiator;
            setState("Waiting for your partner…");
            if (initiator) offer().catch((e) => onError(e.message));
          }),
        );
        socket.on("peer_ready", () => {
          if (initiator) offer().catch((e) => onError(e.message));
        });
        socket.on("signal", async (d) => {
          if (d.appointment !== appointment) return;
          try {
            if (d.signal.description) {
              await connection.setRemoteDescription(d.signal.description);
              for (const c of pending) await connection.addIceCandidate(c);
              pending = [];
              if (d.signal.description.type === "offer") {
                await connection.setLocalDescription(
                  await connection.createAnswer(),
                );
                socket.emit("signal", {
                  appointment,
                  signal: { description: connection.localDescription },
                });
              }
            } else if (d.signal.candidate) {
              if (connection.remoteDescription)
                await connection.addIceCandidate(d.signal.candidate);
              else pending.push(d.signal.candidate);
            }
          } catch (e) {
            onError(e.message);
          }
        });
        socket.on("peer_left", () => setState("Your partner left."));
      } catch (e) {
        onError(e.message);
        setState("Camera unavailable");
      }
    })();
    return () => {
      disposed = true;
      socket?.emit("leave_consultation", { appointment });
      socket?.disconnect();
      connection?.close();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [appointment]);
  return (
    <div className="video">
      <p>{state}</p>
      <div>
        <video ref={local} autoPlay playsInline muted />
        <video ref={remote} autoPlay playsInline />
      </div>
      <button onClick={onClose}>Leave and stop camera</button>
      <small>
        Media is not recorded. Ending sharing does not forcibly terminate an
        already established peer connection; leave the call to stop media.
      </small>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
