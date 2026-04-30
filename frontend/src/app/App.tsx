import { RouterProvider } from 'react-router';
import { AppDataProvider } from './data/AppDataContext';
import { router } from './routes';

export default function App() {
  return (
    <div className="dark">
      <AppDataProvider>
        <RouterProvider router={router} />
      </AppDataProvider>
    </div>
  );
}
