const Charts = {
  instances: {},

  _resolve(key) {
    if (this.instances[key]) {
      this.instances[key].destroy();
      delete this.instances[key];
    }
  },

  create(canvas, config) {
    const key = canvas.id || canvas.parentElement?.id || Math.random().toString(36).slice(2);
    this._resolve(key);
    const chart = new Chart(canvas, config);
    this.instances[key] = chart;
    return chart;
  },

  destroy(canvas) {
    const key = canvas.id || canvas.parentElement?.id;
    if (key && this.instances[key]) {
      this.instances[key].destroy();
      delete this.instances[key];
    }
  },

  clearAll() {
    Object.values(this.instances).forEach(c => c.destroy());
    this.instances = {};
  },

  colors: {
    green: '#22c55e',
    red: '#ef4444',
    blue: '#3b82f6',
    yellow: '#eab308',
    purple: '#8b5cf6',
    teal: '#14b8a6',
    orange: '#f97316',
    gray: '#6b7280',
    darkBg: '#1e2235',
    lightBg: '#ffffff',
    darkBorder: '#2a2e3f',
    lightBorder: '#e5e7eb',
  },

  isDark() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  },

  themeColors() {
    const dark = this.isDark();
    return {
      bg: dark ? this.colors.darkBg : this.colors.lightBg,
      border: dark ? this.colors.darkBorder : this.colors.lightBorder,
      text: dark ? '#e8eaed' : '#1a1a2e',
      grid: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
    };
  },

  doughnut(data, labels, colors, canvas) {
    return this.create(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1.5,
          hoverOffset: 8,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { padding: 10, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              label: ctx => {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = ((ctx.parsed / total) * 100).toFixed(1);
                return ` ${ctx.label}: ${pct}%`;
              },
            },
          },
        },
      },
    });
  },

  horizontalBar(labels, values, colors, canvas, {
    label = '', title = '', prefix = '', suffix = '',
  } = {}) {
    const t = this.themeColors();
    const isSingleColor = typeof colors === 'string';
    return this.create(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label,
          data: values,
          backgroundColor: isSingleColor ? colors : colors,
          borderColor: isSingleColor ? colors : colors.map(() => 'transparent'),
          borderRadius: 2,
          borderSkipped: false,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: !!label, labels: { color: t.text, font: { size: 11 } } },
          title: title ? { display: true, text: title, color: t.text, font: { size: 13, weight: '600' } } : undefined,
          tooltip: {
            callbacks: {
              label: ctx => ` ${prefix}${ctx.parsed.x.toFixed(1)}${suffix}`,
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: t.grid },
            ticks: { color: t.text, font: { size: 10 } },
          },
          y: {
            grid: { display: false },
            ticks: { color: t.text, font: { size: 11 } },
          },
        },
      },
    });
  },

  line(labels, datasets, canvas, { title = '', yLabel = '' } = {}) {
    const t = this.themeColors();
    return this.create(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { labels: { color: t.text, font: { size: 11 } } },
          title: title ? { display: true, text: title, color: t.text, font: { size: 13, weight: '600' } } : undefined,
        },
        scales: {
          x: {
            grid: { color: t.grid },
            ticks: { color: t.text, font: { size: 10 } },
          },
          y: {
            beginAtZero: true,
            title: yLabel ? { display: true, text: yLabel, color: t.text } : undefined,
            grid: { color: t.grid },
            ticks: { color: t.text, font: { size: 10 } },
          },
        },
      },
    });
  },

  verticalBar(labels, datasets, canvas, { title = '', stacked = false } = {}) {
    const t = this.themeColors();
    return this.create(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: datasets.map(d => ({ ...d, borderRadius: 2 })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: t.text, font: { size: 11 } } },
          title: title ? { display: true, text: title, color: t.text, font: { size: 13, weight: '600' } } : undefined,
        },
        scales: {
          x: {
            grid: { color: t.grid },
            ticks: { color: t.text, font: { size: 10 } },
          },
          y: {
            beginAtZero: true,
            stacked,
            grid: { color: t.grid },
            ticks: { color: t.text, font: { size: 10 } },
          },
        },
      },
    });
  },
};
