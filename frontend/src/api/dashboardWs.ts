export interface ViewParams {
  table: string;
  page: number;
  page_size: number;
  sort?: { column: string; desc: boolean };
  filters?: { column: string; op: string; value: unknown }[];
}

export interface DashboardWsEvent {
  event: string;
  widget_id?: string;
  tables?: string[];
  rows?: unknown[];
  columns?: string[];
  total?: number;
  error?: string;
}

export class DashboardWsClient {
  private ws: WebSocket | null = null;
  private onEvent: (event: DashboardWsEvent) => void;

  constructor(pipelineKey: string, onEvent: (event: DashboardWsEvent) => void) {
    this.onEvent = onEvent;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:8000';
    this.ws = new WebSocket(`${protocol}//${host}/ws/dashboard/${pipelineKey}`);
    this.ws.onmessage = (e: MessageEvent) => {
      try {
        this.onEvent(JSON.parse(e.data as string));
      } catch {
        // skip malformed messages
      }
    };
  }

  subscribe(widgetId: string, params: ViewParams) {
    this.ws?.send(JSON.stringify({
      action: 'subscribe',
      widget_id: widgetId,
      ...params,
    }));
  }

  fetch(widgetId: string) {
    this.ws?.send(JSON.stringify({
      action: 'fetch',
      widget_id: widgetId,
    }));
  }

  close() {
    this.ws?.close();
    this.ws = null;
  }
}
