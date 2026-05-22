// ===========================================================================
// Game Detail Page - MLB Predictive System
// ===========================================================================

import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService, EVBet, SimulationResult } from '../../services/api.service';

@Component({
  selector: 'app-game-detail',
  templateUrl: './game-detail.page.html',
})
export class GameDetailPage implements OnInit {
  gameId: string = '';
  game: any = {};
  simulation: SimulationResult | null = null;
  gameBets: EVBet[] = [];

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
  ) {}

  ngOnInit() {
    this.gameId = this.route.snapshot.paramMap.get('game_id') || '';
    this.loadGame();
  }

  loadGame() {
    this.api.getGamePreview().subscribe((games) => {
      this.game = games.find((g) => g.game_id === this.gameId) || {};
    });

    this.api.getSimulation(this.gameId).subscribe((sim) => {
      this.simulation = sim;
    });

    this.api.getApprovedBets().subscribe((bets) => {
      this.gameBets = bets.filter((b) => b.game_id === this.gameId);
    });
  }
}
