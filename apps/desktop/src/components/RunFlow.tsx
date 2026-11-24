import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, CheckCircleIcon, WarningCircleIcon } from "@phosphor-icons/react";
import type { RunFlow as Flow } from "../../../../packages/contracts/generated/typescript/models";
import { useWorkspaceApi } from "../api";
import { researchAgentLabel } from "../researchLabels";

const stageLabels: Record<string, string> = {
  required_data: "获取必要数据",
  supplemental_data: "获取补充数据",
  context: "整理研究上下文",
  agents: "执行分析",
  llm_research: "模型补充研究",
  rules: "检查规则",
  synthesize: "汇总结论",
};
const decisionLabels: Record<string, string> = { WATCH: "观察", NO_ACTION: "暂无动作", BLOCKED: "已阻断" };
const capabilityLabels: Record<string, string> = {
  market_snapshot: "行情快照", trading_calendar: "交易日历", fundamentals: "基本面数据",
  news: "新闻", filings: "公告", company_profile: "公司概况", daily_bars: "日线行情",
  index_series: "指数行情", security_master: "证券基础资料",
};
const statusLabels: Record<Flow["nodes"][number]["status"], string> = {
  pending: "待执行", running: "执行中", completed: "已完成", skipped: "已跳过", failed: "失败", blocked: "已阻断",
};
const relationLabels: Record<Flow["edges"][number]["relation"], string> = {
  sequence: "下一步", depends_on: "依赖", fallback: "切换备用来源", produces: "生成",
};

function nodeLabel(node: Flow["nodes"][number]) {
  if (node.label.startsWith("Decision: ")) {
    const status = node.label.slice("Decision: ".length);
    return `结论：${Object.hasOwn(decisionLabels, status) ? decisionLabels[status] : status}`;
  }
  const capabilityPrefix = `${node.stage_id} / `;
  if (node.label.startsWith(capabilityPrefix) && Object.hasOwn(capabilityLabels, node.stage_id)) {
    return `${capabilityLabels[node.stage_id]} / ${node.label.slice(capabilityPrefix.length)}`;
  }
  return Object.hasOwn(stageLabels, node.label) ? stageLabels[node.label] : researchAgentLabel(node.label);
}

export function RunFlow({ taskId, revision }: { taskId: string; revision: number }) {
  const api = useWorkspaceApi();
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
  }, [api, taskId, revision]);
  const node = flow?.nodes.find((item) => item.id === selected);
  return <details className="run-flow" id="research-flow">
    <summary>执行流程 {flow?.completeness === "legacy_incomplete" ? "· 历史记录不完整" : ""}</summary>
    {error && <p role="status">{error}</p>}
    <ol className="flow-nodes" aria-label="研究执行流程">{flow?.nodes.map((item) => <li key={item.id}>
      <button className="quiet-button flow-node" aria-pressed={selected === item.id}
        onClick={() => setSelected(item.id)} aria-label={`${nodeLabel(item)} ${statusLabels[item.status]}`}>
        {item.status === "completed" ? <CheckCircleIcon size={18} /> : <WarningCircleIcon size={18} />}
        <span>{nodeLabel(item)}<small>{statusLabels[item.status]} · {item.duration_ms == null ? "耗时未知" : `${Math.round(item.duration_ms)} 毫秒`}</small></span>
      </button>
      {flow.edges.filter((edge) => edge.source === item.id).map((edge) => <span className="flow-edge" key={edge.target}>
        <ArrowRightIcon size={14} aria-hidden="true" /> {relationLabels[edge.relation]}
      </span>)}
    </li>)}</ol>
    {node && <div className="flow-selection" role="status">
      <strong>{nodeLabel(node)}</strong>
      <p>{statusLabels[node.status]}</p>
      {!!node.reason_codes?.length && <p>原因代码：{node.reason_codes.join(" · ")}</p>}
      {!!node.artifact_refs?.length && <p>{node.artifact_refs.join(" · ")}</p>}
      <a href="#research-trace">研究过程</a>{" · "}<a href="#research-evidence">依据</a>
    </div>}
  </details>;
}
