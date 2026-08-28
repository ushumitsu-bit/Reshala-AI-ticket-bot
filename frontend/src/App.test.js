import { render, screen } from '@testing-library/react';
import App from './App';

test('рендерится без падения и показывает загрузку', () => {
  render(<App />);
  expect(screen.getByTestId('app-loading')).toBeInTheDocument();
});
