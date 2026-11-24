import { useId, useState, type Ref } from "react";
import { MagnifyingGlassIcon } from "@phosphor-icons/react";
import type { Task } from "../api";
import { stockCode, taskTitle } from "../workspaceResearch";

type Props = {
  inputRef: Ref<HTMLInputElement>;
  query: string;
  setQuery: (query: string) => void;
  instruments: ReadonlyMap<string, string>;
  tasks: Task[];
  latest: ReadonlyMap<string, Task>;
  onSearch: () => void;
  onOpen: (taskId: string) => void;
  onResearch: (symbol: string) => void;
  busy: boolean;
  historyReady: boolean;
};

export function WorkspaceSearch({
  inputRef, query, setQuery, instruments, tasks, latest, onSearch, onOpen, onResearch, busy, historyReady,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const resultsId = useId();
  const term = query.trim().toLowerCase();
  const code = stockCode(term);
  const symbols = term ? [...instruments]
    .filter(([symbol, name]) => symbol.toLowerCase().includes(term) || name.toLowerCase().includes(term))
    .slice(0, 5) : [];
  if (code && !symbols.some(([symbol]) => symbol === code)) symbols.unshift([code, instruments.get(code) ?? ""]);
  const records = term ? tasks.filter((task) =>
    [taskTitle(task, instruments), task.id, task.target.as_of].join(" ").toLowerCase().includes(term),
  ).slice(0, 5) : [];
  const choose = (action: () => void) => {
    setExpanded(false);
    setQuery("");
    action();
  };
  const openSymbol = (symbol: string) => {
    const task = latest.get(symbol);
    if (task) choose(() => onOpen(task.id));
    else if (historyReady) choose(() => onResearch(symbol));
  };

  return <form className="workspace-search" role="search"
    onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setExpanded(false);
    }}
    onKeyDown={(event) => {
      if (event.key === "Escape") setExpanded(false);
    }}
    onSubmit={(event) => {
      event.preventDefault();
      if (!term || busy) return;
      const exact = symbols.filter(([symbol, name]) => symbol === code || name.toLowerCase() === term);
      if (exact.length === 1) openSymbol(exact[0][0]);
      else if (records.length === 1 && symbols.length === 0) choose(() => onOpen(records[0].id));
      else setExpanded(true);
    }}>
    <div className="search-field">
      <MagnifyingGlassIcon size={16} aria-hidden="true" />
      <input ref={inputRef} className="global-search" type="search" autoComplete="off"
        aria-label="搜索名称、代码或研究" placeholder="搜索名称、代码或研究"
        aria-controls={expanded && term ? resultsId : undefined}
        value={query} onFocus={() => { setExpanded(true); onSearch(); }}
        onChange={(event) => { setQuery(event.target.value); setExpanded(true); }} />
    </div>
    {expanded && term && <div className="search-results panel" id={resultsId}>
      {symbols.map(([symbol, name]) => {
        const task = latest.get(symbol);
        return <div className="search-result" key={symbol}>
          <span><strong>{name || symbol}</strong>{name && <small>{symbol}</small>}</span>
          {task && <button type="button" className="quiet-button" onClick={() => choose(() => onOpen(task.id))}>打开研究</button>}
          <button type="button" className="quiet-button" disabled={busy}
            onClick={() => choose(() => onResearch(symbol))}>新建研究</button>
        </div>;
      })}
      {records.map((task) => <button type="button" className="search-record" key={task.id}
        onClick={() => choose(() => onOpen(task.id))}>
        <strong>{taskTitle(task, instruments)}</strong><small>{String(task.target.as_of ?? "")}</small>
      </button>)}
      {!symbols.length && !records.length && <p>暂无匹配。可以输入完整的六位证券代码。</p>}
    </div>}
  </form>;
}
