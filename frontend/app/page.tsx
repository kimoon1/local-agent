"use client";

import { FormEvent, useEffect, useState } from "react";
import "./search-process.css";

type Source = { title: string; url: string; snippet: string };
type SearchTrace = { provider: string; query: string; result_count: number; status: string };
type Message = { role: "user" | "assistant" | "error"; content: string; sources?: Source[]; searchTrace?: SearchTrace[] };
type ModelInfo = { id: string; object: string };
type Settings = { base_url: string; model: string; temperature: number };

const defaultModel = "openai/gpt-oss-20b";
const initialSettings: Settings = { base_url: "http://localhost:1234/v1", model: defaultModel, temperature: 0.2 };

export default function Home() {
  const [settings, setSettings] = useState<Settings>(initialSettings);
  const [showSettings, setShowSettings] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelLog, setModelLog] = useState<string[]>([]);
  const [apiKey, setApiKey] = useState("");

  function writeModelLog(message: string) {
    const time = new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(new Date());
    setModelLog((current) => [`${time}  ${message}`, ...current].slice(0, 6));
  }

  async function loadModels(baseUrl = settings.base_url) {
    setModelLoading(true);
    writeModelLog(`LM Studio 모델 목록 확인 중 (${baseUrl})`);
    try {
      const response = await fetch("/api/models", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey || undefined }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.error || "모델 목록 요청에 실패했습니다.");
      const nextModels: ModelInfo[] = result.models;
      setModels(nextModels);
      const requestedLoaded = nextModels.some((model) => model.id === defaultModel);
      writeModelLog(requestedLoaded
        ? `${defaultModel} 로드 확인 — 총 ${nextModels.length}개 모델 사용 가능`
        : `연결됨 — ${nextModels.length}개 모델 발견. ${defaultModel}은 아직 로드되지 않았습니다.`);
    } catch (error) {
      setModels([]);
      writeModelLog(`연결 실패 — ${(error as Error).message}`);
    } finally {
      setModelLoading(false);
    }
  }

  useEffect(() => {
    try {
      const stored = localStorage.getItem("local-web-agent-settings");
      if (stored) {
        const restored = { ...initialSettings, ...JSON.parse(stored) };
        setSettings(restored);
        void loadModels(restored.base_url);
        return;
      }
    } catch { /* Ignore malformed browser-only settings. */ }
    void loadModels(initialSettings.base_url);
  }, []);

  useEffect(() => localStorage.setItem("local-web-agent-settings", JSON.stringify(settings)), [settings]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const prompt = question.trim();
    if (!prompt || pending) return;
    const history = messages.filter((m) => m.role !== "error").map(({ role, content }) => ({ role, content }));
    setQuestion("");
    setPending(true);
    setMessages((current) => [...current, { role: "user", content: prompt }]);
    try {
      const response = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: prompt, history, ...settings, api_key: apiKey || undefined }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.error || "요청에 실패했습니다.");
      setMessages((current) => [...current, {
        role: "assistant", content: result.answer, sources: result.sources, searchTrace: result.search_trace,
      }]);
    } catch (error) {
      setMessages((current) => [...current, { role: "error", content: `오류: ${(error as Error).message}` }]);
    } finally {
      setPending(false);
    }
  }

  const selectedModelIsLoaded = models.some((model) => model.id === settings.model);

  return <main>
    <header>
      <div><p className="eyebrow">NEXT.JS + FASTAPI + LM STUDIO</p><h1>Local Web Agent</h1></div>
      <button className="secondary" onClick={() => setShowSettings(!showSettings)}>연결 설정</button>
    </header>
    <p className={`connection-summary ${selectedModelIsLoaded ? "connected" : ""}`}>
      {modelLoading ? "LM Studio 모델 목록을 불러오는 중…" : modelLog[0] || "LM Studio 연결을 확인하는 중…"}
    </p>
    {showSettings && <section className="settings">
      <label>LM Studio API 주소
        <input value={settings.base_url} onChange={(e) => setSettings({ ...settings, base_url: e.target.value })} />
      </label>
      <label>LM Studio 모델
        <select value={settings.model} onChange={(e) => setSettings({ ...settings, model: e.target.value })} disabled={modelLoading}>
          {!selectedModelIsLoaded && <option value={settings.model}>{settings.model} (기본 선택)</option>}
          {models.map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
        </select>
      </label>
      <label>LM Studio API 토큰
        <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="인증을 켰을 때만 입력" autoComplete="off" />
      </label>
      <label>창의성
        <input type="number" min="0" max="2" step="0.1" value={settings.temperature} onChange={(e) => setSettings({ ...settings, temperature: Number(e.target.value) })} />
      </label>
      <div className="model-status">
        <button type="button" className="secondary" onClick={() => loadModels()} disabled={modelLoading}>{modelLoading ? "확인 중…" : "모델 새로고침"}</button>
        <div className="model-log" aria-live="polite">
          {modelLog.length ? modelLog.map((entry) => <p key={entry}>{entry}</p>) : <p>모델 상태를 확인하는 중입니다.</p>}
        </div>
      </div>
      <p>토큰은 브라우저에 저장하지 않고 현재 화면에서만 사용합니다. LM Studio에서 <b>{defaultModel}</b>을 로드한 뒤 <b>Start Server</b>를 누르세요.</p>
    </section>}
    <section className="chat">
      {messages.length === 0 && <article className="welcome"><h2>무엇을 알아볼까요?</h2><p>웹을 검색하고 그 근거를 로컬 모델에 전달합니다.</p></article>}
      {messages.map((message, i) => <article key={i} className={`message ${message.role}`}>
        <div className="content">{message.content}</div>
        {message.searchTrace && <details className="search-process" open>
          <summary>검색 과정 · 검색어와 결과 확인</summary>
          <ol>
            {message.searchTrace.map((step, index) => <li key={`${step.query}-${index}`}>
              <b>{step.provider}</b>에서 <code>{step.query}</code> 검색 — {step.result_count}개 결과 ({step.status})
            </li>)}
          </ol>
        </details>}
        {message.sources && <div className="sources"><h3>검색 출처</h3>{message.sources.map((source, j) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">[{j + 1}] {source.title}</a>)}</div>}
      </article>)}
      {pending && <article className="message assistant pending">웹을 검색하고 로컬 모델이 답변을 작성하고 있습니다…</article>}
    </section>
    <form onSubmit={submit}>
      <textarea
        rows={3}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
        placeholder="예: 오늘 엔비디아 관련 주요 뉴스 요약해줘"
        required
      />
      <button disabled={pending}>{pending ? "검색 중…" : "검색하고 답변하기"}</button>
    </form>
  </main>;
}
