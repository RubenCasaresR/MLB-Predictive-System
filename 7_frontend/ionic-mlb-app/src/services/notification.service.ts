// ===========================================================================
// Notification Service - Push y campana local
// ===========================================================================

import { Injectable } from '@angular/core';
import { ApiService, Alert } from './api.service';
import { Subscription } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private alertSub?: Subscription;
  private unreadCount = 0;

  constructor(private api: ApiService) {
    this.subscribe();
  }

  private subscribe() {
    this.alertSub = this.api.alerts$.subscribe((alert: Alert) => {
      this.unreadCount++;
      this.showLocalNotification(alert);
    });
  }

  private showLocalNotification(alert: Alert) {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('MLB Predictive Alert', {
        body: alert.message,
        icon: '/assets/icon.png',
        tag: alert.game_id,
        vibrate: [200, 100, 200],
      });
    }

    if ('vibrate' in navigator) {
      navigator.vibrate(200);
    }
  }

  async requestPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
      await Notification.requestPermission();
    }
  }

  getUnreadCount(): number {
    return this.unreadCount;
  }

  resetUnread() {
    this.unreadCount = 0;
  }

  ngOnDestroy() {
    this.alertSub?.unsubscribe();
  }
}
