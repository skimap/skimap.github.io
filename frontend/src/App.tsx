import { useEffect, useState } from 'react'
import SkiMap from './components/SkiMap'

export interface SkiData {
  ski_areas: Record<string, [number, number]>;
  tile_url: string;
}

function App() {
  const [data, setData] = useState<SkiData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/map_data.json')
      .then(res => res.json())
      .then(data => {
        setData(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load map data", err);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="h-screen w-screen flex items-center justify-center">Loading Ski Data...</div>;
  if (!data) return <div className="h-screen w-screen flex items-center justify-center">Error loading data.</div>;

  return (
    <div className="h-screen w-screen relative">
      <SkiMap data={data} />
    </div>
  )
}

export default App
