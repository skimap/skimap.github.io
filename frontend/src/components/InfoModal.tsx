import React, { useEffect, useRef } from 'react';

interface InfoModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const InfoModal: React.FC<InfoModalProps> = ({ isOpen, onClose }) => {
  const modalRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  // Close on click outside the modal
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm p-4"
      onClick={handleBackdropClick}
    >
      <div 
        ref={modalRef}
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto flex flex-col"
      >
        {/* Fejléc */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-800">A Sítérképről</h2>
          <button 
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 text-gray-600 leading-relaxed">
          <p className="text-lg font-medium text-gray-800">
            Sípályák valódi meredekségének vizualizációja valós GPS nyomvonalak alapján.
          </p>

          <div className="bg-blue-50 p-4 rounded-md border-l-4 border-blue-500">
            <h3 className="font-bold text-blue-800 mb-2">Hogyan működik?</h3>
            <p className="text-sm">
              Síelők által rögzített valós GPS nyomvonalakat dolgozunk fel a pályák tényleges meredekségének kiszámításához. 
              A térképen látható színek a lejtő dőlésszögét jelölik, ami pontosabb képet ad a nehézségről, mint a hagyományos jelölések.
            </p>
          </div>

          <h3 className="text-xl font-semibold text-gray-800 mt-4">Színmagyarázat</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="flex items-center"><span className="w-4 h-4 rounded-full bg-gray-400 mr-2"></span> Hegymenet / Lapos</div>
            <div className="flex items-center"><span className="w-4 h-4 rounded-full bg-green-500 mr-2"></span> Nagyon könnyű (Zöld)</div>
            <div className="flex items-center"><span className="w-4 h-4 rounded-full bg-blue-500 mr-2"></span> Könnyű (Kék)</div>
            <div className="flex items-center"><span className="w-4 h-4 rounded-full bg-red-600 mr-2"></span> Közepes (Piros)</div>
            <div className="flex items-center"><span className="w-4 h-4 rounded-full bg-black mr-2"></span> Nehéz (Fekete)</div>
          </div>

          <h3 className="text-xl font-semibold text-gray-800 mt-4">Készítők</h3>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>Ötlet:</strong> Zsélyé Ujvári Mária</li>
            <li><strong>Fejlesztés:</strong> Zsély Bence és Zsély István</li>
            <li><strong>Adatok:</strong> OpenSkiMap.org és közösségi beküldések</li>
          </ul>

          <p className="text-xs text-gray-400 mt-8 border-t pt-4">
            A projekt forráskódja nyílt, elérhető a <a href='https://github.com/skimap/skimap.github.io' className='text-blue-500 hover:underline'>GitHubon</a>.
          </p>
        </div>
      </div>
    </div>
  );
};

export default InfoModal;