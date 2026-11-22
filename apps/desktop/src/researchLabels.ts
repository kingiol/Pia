const agentLabels: Record<string, string> = {
  "Investment Chief": "研究统筹",
  "Market Analyst": "市场分析",
  "Sector Analyst": "板块分析",
  "Portfolio Analyst": "持仓分析",
  "Technical Analyst": "技术分析",
  "Stock Researcher": "个股研究",
  "News Analyst": "新闻与公告分析",
  "Bull Case Analyst": "看多分析",
  "Bear Case Analyst": "看空分析",
  "Debate Chair": "多空观点汇总",
  "Research Manager": "研究汇总",
  "Risk / Rules Agent": "风险与规则审核",
  "Decision Agent": "决策汇总",
  "LLM Research Manager": "模型补充研究",
  "Final decision": "最终结论",
};

export function researchAgentLabel(name: string) {
  return Object.hasOwn(agentLabels, name) ? agentLabels[name] : name;
}
