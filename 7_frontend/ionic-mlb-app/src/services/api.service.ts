// ===========================================================================
// API Service - MLB Predictive System
// ===========================================================================

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, interval, Subject } from 'rxjs';
import { switchMap, startWith } from 'rxjs/operators';

export interface EVBet {
  game_id: string;
  team: string;
  opponent: string;
  sportsbook: string;
  market_type: string;
  odds: number;
  edge: number;
  kelly_fraction: number;
  recommended_stake: number;
  confidence: number;
  is_actionable: boolean;
}

export interface SimulationResult {
  game_id: string;
  home_win_prob: number;
  away_win_prob: number;
  mean_home_runs: number;
  mean_away_runs: number;
  extra_innings_prob: number;
}

export interface Alert {
  alert_id: number;
  game_id: string;
  team_id: string;
  signal_type: string;
  confidence: number;
  message: string;
  created_at: string;
  is_read: boolean;
}

export interface BankrollStatus {
  current: number;
  peak: number;
  drawdown_pct: number;
  roi_pct: number;
  bet_count: number;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = 'http://localhost:8000/api/v1';
  private wsUrl = 'ws://localhost:8000/api/v1/alerts/ws';

  private alertSubject = new Subject<Alert>();
  public alerts$ = this.alertSubject.asObservable();

  constructor(private http: HttpClient) {
    this.connectWebSocket();
  }

  // ==========================================================================
  // REST ENDPOINTS
  // ==========================================================================

  getApprovedBets(minEdge = 0.02): Observable<EVBet[]> {
    return this.http.get<EVBet[]>(`${this.baseUrl}/bets/approved`, {
      params: { min_edge: minEdge },
    });
  }

  getSimulation(gameId: string): Observable<SimulationResult> {
    return this.http.post<SimulationResult>(`${this.baseUrl}/bets/simulate`, {
      game_id: gameId,
    });
  }

  getAlerts(unreadOnly = false): Observable<{ alerts: Alert[]; total: number; unread_count: number }> {
    return this.http.get<{ alerts: Alert[]; total: number; unread_count: number }>(
      `${this.baseUrl}/alerts`,
      { params: { unread_only: unreadOnly ? 'true' : 'false' } },
    );
  }

  getBankroll(): Observable<BankrollStatus> {
    return this.http.get<BankrollStatus>(`${this.baseUrl}/risk/bankroll`);
  }

  getGamePreview(date?: string): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/stats/preview`, {
      params: date ? { date } : {},
    });
  }

  pollBets(intervalMs = 30000): Observable<EVBet[]> {
    return interval(intervalMs).pipe(
      startWith(0),
      switchMap(() => this.getApprovedBets()),
    );
  }

  // ==========================================================================
  // WEBSOCKET (Real-time alerts)
  // ==========================================================================

  private connectWebSocket() {
    try {
      const ws = new WebSocket(this.wsUrl);

      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: 'subscribe',
          channels: ['sharp_money', 'ev_positive', 'rlm'],
        }));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'alert' || data.type === 'ev_alert') {
          this.alertSubject.next({
            alert_id: Date.now(),
            game_id: data.game_id,
            team_id: data.team_id || data.team,
            signal_type: data.signal_type || 'EV_POSITIVE',
            confidence: data.confidence || data.edge || 0,
            message: data.message,
            created_at: data.timestamp || new Date().toISOString(),
            is_read: false,
          });
        }
      };

      ws.onclose = () => {
        setTimeout(() => this.connectWebSocket(), 5000);
      };
    } catch (e) {
      console.error('WebSocket connection failed', e);
    }
  }
}
