import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import Landing from './Landing';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {window.location.pathname === '/work' || window.location.pathname.startsWith('/work/') ? <App /> : <Landing />}
  </React.StrictMode>,
);
