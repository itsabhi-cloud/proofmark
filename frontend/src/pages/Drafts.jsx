import { useState } from "react";
import { api, timeAgo } from "../api.js";
import { Button, Empty, ErrorNote, Link, Loading, PageHeader, Status, navigate, useApp, useAsync } from "../ui.jsx";

const FILTERS = [
  ["all", "All"],
  ["draft", "Drafts"],
  ["in_review", "In review"],
  ["changes_requested", "Changes requested"],
  ["approved", "Approved"],
];

export default function Drafts({ reviewQueue }) {
  const { user } = useApp();
  const { data, loading, error } = useAsync(() => api("/drafts"), [reviewQueue]);
  const [filter, setFilter] = useState("all");

  const drafts = (data?.drafts || []).filter((d) =>
    reviewQueue ? d.status === "in_review" && d.creator_id !== user.id : filter === "all" || d.status === filter
  );

  const title = reviewQueue ? "Review queue" : user.role === "creator" ? "My drafts" : "All drafts";
  const lead = reviewQueue
    ? "Drafts waiting for your decision. Findings are already attached."
    : user.role === "creator"
    ? "Scan a draft before you submit it. Reviewers see the same evidence you do."
    : "Every draft across the brand, with its current status.";

  return (
    <>
      <PageHeader title={title} lead={lead}>
        {["creator", "owner"].includes(user.role) && !reviewQueue ? (
          <Button variant="primary" onClick={() => navigate("/new")}>
            New draft
          </Button>
        ) : null}
      </PageHeader>
      {!reviewQueue ? (
        <div className="filters" role="group" aria-label="Filter by status">
          {FILTERS.map(([k, label]) => (
            <button key={k} className={`chip ${filter === k ? "chip-on" : ""}`} onClick={() => setFilter(k)}
              aria-pressed={filter === k}>
              {label}
            </button>
          ))}
        </div>
      ) : null}
      <ErrorNote error={error} />
      {loading ? (
        <Loading />
      ) : drafts.length === 0 ? (
        <Empty title={reviewQueue ? "Nothing waiting for review" : "No drafts here yet"}>
          {reviewQueue ? (
            <p>When a creator submits a draft, it appears here.</p>
          ) : ["creator", "owner"].includes(user.role) ? (
            <p>
              <Link to="/new">Write or upload a draft</Link> and Proofmark will scan it straight away.
            </p>
          ) : (
            <p>Drafts appear here once creators start writing.</p>
          )}
        </Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Draft</th>
                <th scope="col">Type</th>
                <th scope="col">Creator</th>
                <th scope="col">Open issues</th>
                <th scope="col">Status</th>
                <th scope="col">Updated</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d) => (
                <tr key={d.id} className="row-link" onClick={() => navigate(`/drafts/${d.id}`)}>
                  <td>
                    <Link to={`/drafts/${d.id}`} className="strong" onClick={(e) => e.stopPropagation()}>
                      {d.title}
                    </Link>
                    <span className="muted small"> v{d.version}</span>
                  </td>
                  <td>{d.content_type}</td>
                  <td>
                    {d.creator_name}
                    <span className="muted small block">{d.creator_team}</span>
                  </td>
                  <td>
                    {d.open_issues ? (
                      <span className={d.high_issues ? "count-high" : "count"}>
                        {d.open_issues}
                        {d.high_issues ? ` (${d.high_issues} high)` : ""}
                      </span>
                    ) : (
                      <span className="count-zero">None</span>
                    )}
                  </td>
                  <td>
                    <Status status={d.status} />
                  </td>
                  <td className="muted">{timeAgo(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
