// ===========================================================================
// App Module - MLB Predictive System
// ===========================================================================

import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { IonicModule } from '@ionic/angular';
import { RouterModule } from '@angular/router';

import { AppComponent } from './app.component';
import { DashboardPage } from '../pages/dashboard/dashboard.page';
import { GameDetailPage } from '../pages/game-detail/game-detail.page';
import { AlertsPage } from '../pages/alerts/alerts.page';

@NgModule({
  declarations: [
    AppComponent,
    DashboardPage,
    GameDetailPage,
    AlertsPage,
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    IonicModule.forRoot({
      mode: 'md',
      animated: true,
    }),
    RouterModule.forRoot([
      { path: '', component: DashboardPage },
      { path: 'game/:game_id', component: GameDetailPage },
      { path: 'alerts', component: AlertsPage },
    ]),
  ],
  providers: [],
  bootstrap: [AppComponent],
})
export class AppModule {}
