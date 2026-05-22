// ===========================================================================
// Alerts Page - MLB Predictive System
// ===========================================================================

import { Component, OnInit } from '@angular/core';
import { ApiService, Alert } from '../../services/api.service';

@Component({
  selector: 'app-alerts',
  templateUrl: './alerts.page.html',
})
export class AlertsPage implements OnInit {
  alerts: Alert[] = [];

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadAlerts();
  }

  loadAlerts() {
    this.api.getAlerts().subscribe((res) => {
      this.alerts = res.alerts;
    });
  }

  markAllRead() {
    this.alerts.forEach((a) => (a.is_read = true));
  }

  getSignalColor(type: string): string {
    switch (type) {
      case 'SHARP_MONEY': return 'tertiary';
      case 'RLM': return 'warning';
      case 'BOTH': return 'danger';
      case 'EV_POSITIVE': return 'success';
      default: return 'medium';
    }
  }
}
