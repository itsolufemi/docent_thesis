import React from 'react';

export default function StartScreen({ loading, handleStartClick }) {
  return (
    <section className="start-screen">
      <button
        type="button"
        className="round-button"
        disabled={loading}
        onClick={handleStartClick}
      >
        {loading ? '...' : '▶'}
      </button>
    </section>
  );
}
