// ===========================================================================
// Dashboard Page - MLB Predictive System
// ===========================================================================

import { Component, OnInit, OnDestroy } from '@angular/core';
import { ApiService, EVBet, BankrollStatus } from '../../services/api.service';
import { NotificationService } from '../../services/notification.service';
import { Subscription, interval } from 'rxjs';
import { startWith, switchMap } from 'rxjs/operators';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.page.html',
})
export class DashboardPage implements OnInit, OnDestroy {
  bankroll: BankrollStatus = {
    current: 0, peak: 0, drawdown_pct: 0,
    roi_pct: 0, bet_count: 0,
  };
  games: any[] = [];
  evBets: EVBet[] = [];
  unreadCount = 0;

  private pollSub?: Subscription;
  private alertSub?: Subscription;

  constructor(
    private api: ApiService,
    private notification: NotificationService,
  ) {}

  ngOnInit() {
    this.loadData();
    this.startPolling();

    this.alertSub = this.api.alerts$.subscribe(() => {
      this.unreadCount = this.notification.getUnreadCount();
    });
  }

  ngOnDestroy() {
    this.pollSub?.unsubscribe();
    this.alertSub?.unsubscribe();
  }

  loadData() {
    this.api.getBankroll().subscribe({
      next: (b) => (this.bankroll = b),
      error: () => console.log('Bankroll API not ready'),
    });

    this.api.getGamePreview().subscribe({
      next: (g) => (this.games = g),
      error: () => console.log('Games API not ready'),
    });

    this.api.getApprovedBets().subscribe({
      next: (b) => (this.evBets = b),
      error: () => console.log('Bets API not ready'),
    });
  }

  startPolling() {
    this.pollSub = interval(30000).subscribe(() => {
      this.api.getApprovedBets().subscribe((b) => (this.evBets = b));
      this.api.getBankroll().subscribe((b) => (this.bankroll = b));
    });
  }

  refresh() {
    this.loadData();
  }

  openAlerts() {
    this.notification.resetUnread();
    this.unreadCount = 0;
  }
}
