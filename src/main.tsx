import {createRoot} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import App from './App.tsx';
import {initRuntimeConfig} from './api.ts';
import './index.css';

initRuntimeConfig();

createRoot(document.getElementById('root')!).render(
  <MemoryRouter>
    <App />
  </MemoryRouter>,
);
