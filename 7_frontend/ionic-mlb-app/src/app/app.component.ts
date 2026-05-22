// ===========================================================================
// App Component - MLB Predictive System
// ===========================================================================

import { Component } from '@angular/core';
import { NotificationService } from '../services/notification.service';

@Component({
  selector: 'app-root',
  template: `
    <ion-app>
      <ion-router-outlet></ion-router-outlet>
    </ion-app>
  `,
})
export class AppComponent {
  constructor(private notification: NotificationService) {
    this.notification.requestPermission();
  }
}
