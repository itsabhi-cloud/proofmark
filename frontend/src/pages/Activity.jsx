import { api, ROLE_LABEL } from "../api.js";
import { ErrorNote, Link, Loading, PageHeader, useAsync } from "../ui.jsx";

export default function Activity() {
  const { data, loading, error } = useAsync(() => api("/activity"), []);
  return (
    <>
      <PageHeader title="Activity log" lead="Every scan, fix, override and approval, with who did it and when." />
      <ErrorNote error={error} />
      {loading ? <Loading /> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">What</th><th scope="col">Draft</th></tr></thead>
            <tbody>
              {data.events.map((e) => (
                <tr key={e.id}>
                  <td className="muted nowrap">{new Date(e.created_at).toLocaleString()}</td>
                  <td>{e.user_name || "System"}{e.user_role ? <span className="muted small block">{ROLE_LABEL[e.user_role]}</span> : null}</td>
                  <td>{e.action}{e.detail ? <span className="muted">: {e.detail}</span> : null}</td>
                  <td>{e.draft_id ? <Link to={`/drafts/${e.draft_id}`}>{e.draft_title}</Link> : <span className="muted">Rulebook</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
