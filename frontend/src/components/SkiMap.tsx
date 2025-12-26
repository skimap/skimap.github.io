import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';
import iconRetina from 'leaflet/dist/images/marker-icon-2x.png';

import {useState, useEffect} from 'react'
import {MapContainer, TileLayer, useMap, Marker, Popup} from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import {SkiData} from '../App'
import SkiAreaSelector from './SkiAreaSelector'
import InfoModal from './InfoModal'

L.Icon.Default.mergeOptions({
    iconRetinaUrl: iconRetina,
    iconUrl: icon,
    shadowUrl: iconShadow,
});

interface SkiMapProps {
    data: SkiData;
}

function FlyToLocation({target}: { target: [number, number] | null }) {
    const map = useMap();
    useEffect(() => {
        if (target) {
            map.flyTo(target, 13, {animate: true, duration: 1.5});
        }
    }, [target, map]);
    return null;
}

function LocateControl({ map }: { map: L.Map | null }) {
    const handleLocate = () => {
        if (map) {
            map.locate({setView: true, maxZoom: 16});
        }
    };

    return (
        <div className="leaflet-control leaflet-bar pointer-events-auto m-0 shadow-md">
            <button
                onClick={handleLocate}
                className="bg-white hover:bg-gray-100 w-[38px] h-[38px] flex items-center justify-center cursor-pointer border-none rounded-md"
                title="Show my location"
            >
                <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none"
                     strokeLinecap="round" strokeLinejoin="round" className="text-gray-700">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M12 2L12 5M12 19L12 22M2 12L5 12M19 12L22 12"></path>
                </svg>
            </button>
        </div>
    );
}

function InfoControl({ onClick }: { onClick: () => void }) {
    return (
        <div className="leaflet-control leaflet-bar pointer-events-auto m-0 shadow-md">
            <button
                onClick={onClick}
                className="bg-white hover:bg-gray-100 w-[38px] h-[38px] flex items-center justify-center cursor-pointer border-none rounded-md"
                title="About SkiMap"
            >
                <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none" 
                     strokeLinecap="round" strokeLinejoin="round" className="text-blue-600">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="16" x2="12" y2="12"></line>
                    <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
            </button>
        </div>
    );
}

export default function SkiMap({data}: SkiMapProps) {
    const [target, setTarget] = useState<[number, number] | null>(null);
    const [map, setMap] = useState<L.Map | null>(null);
    const [isInfoOpen, setIsInfoOpen] = useState(false);

    return (
        <div className="relative w-full h-full">
            <InfoModal isOpen={isInfoOpen} onClose={() => setIsInfoOpen(false)} />
            
            <MapContainer
                center={[47.85, 16.01]}
                zoom={6}
                scrollWheelZoom={true}
                className="w-full h-full z-0"
                preferCanvas={true}
                ref={setMap}
            >
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                    url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                    subdomains="abcd"
                />

                <TileLayer
                    attribution='Ski Tracks'
                    url={data.tile_url}
                    minZoom={6}
                    maxZoom={19}
                    opacity={0.9}
                    eventHandlers={{
                        tileerror: (e) => {
                            console.log({e})
                        }
                    }}
                />

                <MarkerClusterGroup chunkedLoading>
                    {Object.entries(data.ski_areas).map(([name, coords]) => (
                        <Marker 
                            key={name} 
                            position={coords}
                            eventHandlers={{
                                click: () => {
                                    setTarget(coords);
                                },
                            }}
                        >
                            <Popup>{name}</Popup>
                        </Marker>
                    ))}
                </MarkerClusterGroup>

                <FlyToLocation target={target}/>
            </MapContainer>

            {/* Overlay Controls */}
            <div className="absolute top-2 right-2 z-[1000] flex flex-row items-center gap-2">
                <div className="w-[250px] sm:w-[300px]">
                    <SkiAreaSelector
                        areas={data.ski_areas}
                        onSelect={(coords) => setTarget(coords)}
                    />
                </div>
                <LocateControl map={map} />
                <InfoControl onClick={() => setIsInfoOpen(true)} />
            </div>
        </div>
    )
}