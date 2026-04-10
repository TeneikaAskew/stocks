import { useState, useRef, useEffect, useMemo } from 'react';
import { marked } from 'marked';
import { useTickerStore } from '@/stores/tickerStore';
import { Send, BarChart2, TrendingUp, BookOpen, MessageSquare, Loader2 } from 'lucide-react';

type Mode = 'chat' | 'market' | 'strategy' | 'trade';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const MODE_CONFIG: Record<Mode, { label: string; icon: React.ReactNode; placeholder: string; quickActions: string[] }> = {
  chat: {
    label: 'Open Chat',
    icon: <MessageSquare size={14} />,
    placeholder: 'Ask anything about your trading data, strategies, or market structure…',
    quickActions: [
      'What are the key levels for today?',
      'Review my recent performance',
      'What patterns should I watch for?',
      'Explain GEX and how it affects price',
    ],
  },
  market: {
    label: 'Market Brief',
    icon: <BarChart2 size={14} />,
    placeholder: 'Ask about current market structure, key levels, or options flow…',
    quickActions: [
      'Give me a market structure brief',
      'Where are the key support/resistance levels?',
      'What does the options flow say?',
      'Is this a trending or ranging day?',
    ],
  },
  strategy: {
    label: 'Strategy',
    icon: <TrendingUp size={14} />,
    placeholder: 'Ask for feedback on your backtest results or strategy improvements…',
    quickActions: [
      'Evaluate my backtest results',
      'How can I improve my win rate?',
      'What are the weakest conditions in my strategy?',
      'Is this strategy robust enough to trade live?',
    ],
  },
  trade: {
    label: 'Trade Review',
    icon: <BookOpen size={14} />,
    placeholder: 'Describe a trade for AI review — entry, exit, setup quality…',
    quickActions: [
      'Review my last trade entry',
      'Was my exit optimal?',
      'Grade this setup A-F',
      'What would you have done differently?',
    ],
  },
};

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user';

  const html = useMemo(() => {
    if (isUser) return '';
    return marked.parse(msg.content) as string;
  }, [msg.content, isUser]);

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {isUser ? (
        <div
          className="max-w-[85%] rounded-lg px-4 py-2.5 text-sm leading-relaxed bg-[var(--color-accent-blue)] text-white"
          style={{ whiteSpace: 'pre-wrap' }}
        >
          {msg.content}
        </div>
      ) : (
        <div
          className="prose-report max-w-[85%] rounded-lg px-4 py-2.5 bg-[var(--color-bg-tertiary)]"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1.5 rounded-lg bg-[var(--color-bg-tertiary)] px-4 py-3">
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-text-muted)]"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export default function InsightsPage() {
  const { activeTicker } = useTickerStore();
  const [mode, setMode] = useState<Mode>('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  useEffect(() => {
    setMessages([]);
  }, [mode, activeTicker]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isStreaming) return;

    const userMsg: Message = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsStreaming(true);

    const assistantMsg: Message = { role: 'assistant', content: '' };
    setMessages(prev => [...prev, assistantMsg]);

    try {
      const res = await fetch('/api/insights/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          mode,
          ticker: activeTicker,
          history: messages.slice(-6).map(m => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) {
        const err = await res.text();
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: 'assistant',
            content: `Error: ${err || 'AI service unavailable. Configure Vertex AI Gemini to enable this feature.'}`,
          };
          return updated;
        });
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No stream');

      let accumulated = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        accumulated += decoder.decode(value, { stream: true });
        const snapshot = accumulated;
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: snapshot };
          return updated;
        });
      }
    } catch {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: 'assistant',
          content: 'AI service unavailable. Enable Vertex AI Gemini on GCP to use this feature.',
        };
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const cfg = MODE_CONFIG[mode];

  return (
    <div className="flex h-full flex-col gap-3" style={{ maxHeight: 'calc(100vh - 120px)' }}>
      {/* Mode selector */}
      <div className="flex flex-wrap items-center gap-2">
        {(Object.entries(MODE_CONFIG) as [Mode, typeof MODE_CONFIG[Mode]][]).map(([m, c]) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium ${
              mode === m
                ? 'bg-[var(--color-accent-blue)] text-white'
                : 'border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'
            }`}
          >
            {c.icon}
            {c.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-[var(--color-text-muted)]">
          Vertex AI Gemini · {activeTicker}
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4">
            <div className="text-center">
              <div className="mb-2 text-3xl">🤖</div>
              <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
                {cfg.label} Mode
              </h3>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                AI quant/trader grounded in your {activeTicker} data
              </p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {cfg.quickActions.map(action => (
                <button
                  key={action}
                  onClick={() => sendMessage(action)}
                  className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-left text-xs text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent-blue)] hover:text-[var(--color-text-primary)]"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}
            {isStreaming && messages[messages.length - 1]?.content === '' && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={cfg.placeholder}
          rows={2}
          className="flex-1 resize-none rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent-blue)] focus:outline-none"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || isStreaming}
          className="flex items-center gap-2 rounded-lg bg-[var(--color-accent-blue)] px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {isStreaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </div>
      <p className="text-center text-[10px] text-[var(--color-text-muted)]">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
