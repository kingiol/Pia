import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, CheckCircleIcon, WarningCircleIcon } from "@phosphor-icons/react";
import type { RunFlow as Flow } from "../../../../packages/contracts/generated/typescript/models";
import { api } from "../api";

export function RunFlow({ taskId, revision }: { taskId: string; revision: number }) {
  const [flow, setFlow] = useState<Flow | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const cache = useRef<Flow | null>(null);
  useEffect(() => {
    let active = true;
    const load = async () => {
      const prior = cache.current?.task_id === taskId ? cache.current : null;
      const first = await api.taskFlow(taskId, prior?.next_after_seq ?? 0);
      const nodes = new Map((prior?.nodes ?? []).map((node) => [node.id, node]));
      const edges = new Map((prior?.edges ?? []).map((edge) => [`${edge.source}:${edge.target}`, edge]));
      first.nodes.forEach((node) => nodes.set(node.id, node));
      first.edges.forEach((edge) => edges.set(`${edge.source}:${edge.target}`, edge));
      let page = first;
      while (page.has_more) {
        page = await api.taskFlow(taskId, page.next_after_seq, 100, first.snapshot_seq);
        page.nodes.forEach((node) => nodes.set(node.id, node));
        page.edges.forEach((edge) => edges.set(`${edge.source}:${edge.target}`, edge));
      }
      if (active) {
        const merged = { ...page, nodes: [...nodes.values()], edges: [...edges.values()] };
        cache.current = merged;
        setFlow(merged);
        setError("");
      }
    };
    void load().catch(() => { if (active) setError("执行流程暂不可用"); });
    return () => { active = false; };
  }, [taskId, revision]);
  const node = flow?.nodes.find((item) => item.id === selected);
  return <details className="run-flow" id="research-flow">
    <summary>执行流程 {flow?.completeness === "legacy_incomplete" ? "· 历史记录不完整" : ""}</summary>
    {error && <p role="status">{error}</p>}
    <ol className="flow-nodes" aria-label="研究执行流程">{flow?.nodes.map((item) => <li key={item.id}>
      <button className="quiet-button flow-node" aria-pressed={selected === item.id}
        onClick={() => setSelected(item.id)} aria-label={`${item.label} ${item.status}`}>
        {item.status === "completed" ? <CheckCircleIcon size={18} /> : <WarningCircleIcon size={18} />}
        <span>{item.label}<small>{item.status} · {item.duration_ms == null ? "耗时未知" : `${Math.round(item.duration_ms)} ms`}</small></span>
      </button>
      {flow.edges.filter((edge) => edge.source === item.id).map((edge) => <span className="flow-edge" key={edge.target}>
        <ArrowRightIcon size={14} aria-hidden="true" /> {edge.relation}
      </span>)}
    </li>)}</ol>
    {node && <div className="flow-selection" role="status">
      <strong>{node.label}</strong>
      <p>{node.reason_codes?.join(" · ") || node.status}</p>
      {!!node.artifact_refs?.length && <p>{node.artifact_refs.join(" · ")}</p>}
      <a href="#research-trace">研究过程</a>{" · "}<a href="#research-evidence">依据</a>
    </div>}
  </details>;
}
