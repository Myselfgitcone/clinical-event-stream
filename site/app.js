// Reads the two feeds the pipeline publishes and fills the page. No framework.
const PORTFOLIO_URL = "https://jagadish-butukuri.vercel.app";
const $ = (id) => document.getElementById(id);
const n = (x) => (x == null ? "–" : Number(x).toLocaleString("en-US"));
const pct = (x) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);

function ago(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.round(ms / 6e4);
  if (m < 60) return `${Math.max(m, 1)} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

function fill(tableId, rows, cells) {
  const body = $(tableId).querySelector("tbody");
  body.innerHTML = "";
  if (!rows || !rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="9" class="note">none</td>`;
    body.appendChild(tr);
    return;
  }
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = cells(r).map(([v, cls]) => `<td class="${cls || ""}">${v}</td>`).join("");
    body.appendChild(tr);
  }
}

function spark(points) {
  const svg = $("spark");
  svg.innerHTML = "";
  const vals = points.map((p) => p.patients || 0);
  if (!vals.length) return;
  const W = 600, H = 160, padX = 8, padT = 14, padB = 24;
  const max = Math.max(...vals, 1);
  const x = (i) => (vals.length === 1 ? W / 2 : padX + (i / (vals.length - 1)) * (W - padX * 2));
  const y = (v) => H - padB - (v / max) * (H - padT - padB);
  const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  svg.innerHTML =
    `<path class="area" d="M${x(0)},${H - padB} L${pts.join(" L")} L${x(vals.length - 1)},${H - padB} Z"/>` +
    `<path d="M${pts.join(" L")}"/>` +
    vals.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="3.5"/>`).join("") +
    `<text x="${padX}" y="${H - 6}">${points[0].week_start}</text>` +
    `<text x="${W - padX}" y="${H - 6}" text-anchor="end">${points[points.length - 1].week_start}</text>` +
    `<text x="${padX}" y="${padT - 3}">${n(max)} patients in the busiest week</text>`;
}

async function read(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function main() {
  let s;
  try {
    s = await read("data/summary.json");
  } catch (e) {
    $("fresh").textContent = "summary.json is not published yet";
    $("fresh-line").classList.add("down");
    return;
  }
  $("hub-link").href = s.portfolio_url || PORTFOLIO_URL;
  $("hub-link").classList.remove("hidden");
  const v = s.volumes || {};
  const cohorts = s.cohorts || [];
  $("fresh").textContent = `Rebuilt ${ago(s.generated_at)} · ${cohorts.length} cohort${cohorts.length === 1 ? "" : "s"} · ${n(s.dbt?.models)} dbt models · ${(s.warehouse_bytes / 1e6).toFixed(0)} MB warehouse`;
  fill("cohorts", cohorts, (r) => [[`<span class="pill">${r.cohort_id}</span>`], [n(r.bundles), "r"], [r.seconds == null ? "–" : Number(r.seconds).toFixed(0), "r"]]);
  $("t-patients").textContent = n(v.patients);
  $("t-encounters").textContent = n(v.encounters);
  $("t-observations").textContent = n(v.observations);
  $("t-conditions").textContent = n(v.conditions);
  $("t-quarantine").textContent = n(v.quarantine);
  const t = s.dbt || {};
  $("t-tests").textContent = t.tests ? `${n(t.tests_passed)}/${n(t.tests)}` : "–";
  if (t.tests) {
    const failed = (t.failures || []).length;
    $("t-tests-d").textContent = failed ? `${failed} failed on the last run` : t.tests_warned ? `${t.tests_warned} warning, none failed` : "all passed on the last run";
  }

  const pairs = s.condition_pairs || [];
  const maxShare = Math.max(...pairs.map((r) => r.share_of_patients || 0), 0.0001);
  fill("pairs", pairs, (r) => [
    [`${r.condition_a}<span class="plus">+</span>${r.condition_b}`],
    [n(r.patients_with_both), "r"],
    [pct(r.share_of_patients), "r"],
    [r.lift == null ? "–" : Number(r.lift).toFixed(2), "r"],
    [`<div class="bar"><span style="width:${(((r.share_of_patients || 0) / maxShare) * 100).toFixed(0)}%"></span></div>`, "hide-sm"],
  ]);

  const cg = s.care_gaps || {};
  $("g-statin").textContent = pct(cg.statin_within_year_share);
  $("g-statin-den").textContent = `${n(cg.statin_within_year)} of ${n(cg.statin_eligible)} eligible`;
  $("g-a1c").textContent = pct(cg.a1c_within_90d_share);
  $("g-a1c-den").textContent = `${n(cg.a1c_within_90d)} of ${n(cg.diabetics)} diabetics`;
  fill("gaps", cg.by_payer_type, (r) => [[r.payer_type], [n(r.diabetics), "r"], [pct(r.statin_share), "r"], [pct(r.a1c_share), "r"]]);
  fill("gaps-age", cg.by_age_band, (r) => [[r.age_band], [n(r.diabetics), "r"], [pct(r.statin_share), "r"], [pct(r.a1c_share), "r"]]);

  const d = s.deid || {};
  fill("deid", d.tables, (r) => [
    [r.table_name],
    [n(r.rows), "r"],
    [n(r.pseudonymised_values), "r"],
    [n(r.shifted_dates), "r"],
    [`<span class="dropped">${(r.dropped_fields || "").split(",").join(", ") || "–"}</span>`],
  ]);
  const k = d.k_anonymity || {};
  if (k.patients) {
    $("k-anon").textContent =
      `k-anonymity on {${k.quasi_identifiers}}: smallest group ${n(k.min_group_size)}, ` +
      `${pct(k.share_in_groups_under_5)} of patients sit in groups under 5, ${n(k.unique_patients)} are unique. ` +
      `Safe Harbor removes direct identifiers; it does not make a record anonymous.`;
  }

  fill("quarantine", s.quarantine_reasons, (r) => [[r.contract], [r.reason], [n(r.rows), "r"]]);
  const skipped = Object.entries(s.skipped_resource_types || {}).sort((a, b) => b[1] - a[1]).map(([t, c]) => ({ t, c }));
  fill("skipped", skipped, (r) => [[r.t], [n(r.c), "r"]]);

  try {
    const w = await read("data/weekly.json");
    spark(w);
    const last = w[w.length - 1];
    $("spark-note").textContent = `${w.length} week${w.length === 1 ? "" : "s"} in the series · latest week ${last.week_start}: ${n(last.patients)} patients, ${n(last.encounters)} encounters, ${n(last.quarantine)} quarantined`;
  } catch {
    $("spark-note").textContent = "weekly.json is not published yet";
  }
}
main();
