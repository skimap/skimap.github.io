import React from 'react';
import Select, { SingleValue } from 'react-select';

interface SkiAreaSelectorProps {
  areas: Record<string, [number, number]>;
  onSelect: (coords: [number, number]) => void;
}

interface Option {
  value: string;
  label: string;
  coords: [number, number];
}

const SkiAreaSelector: React.FC<SkiAreaSelectorProps> = ({ areas, onSelect }) => {
  const options: Option[] = Object.entries(areas)
    .sort(([nameA], [nameB]) => nameA.localeCompare(nameB))
    .map(([name, coords]) => ({
      value: name,
      label: name,
      coords: coords
    }));

  const handleChange = (selectedOption: SingleValue<Option>) => {
    if (selectedOption) {
      onSelect(selectedOption.coords);
    }
  };

  return (
    <div className="bg-white rounded-md shadow-md p-1 border border-gray-300">
      <Select
        options={options}
        onChange={handleChange}
        placeholder="Search Ski Areas..."
        isClearable={true}
        className="text-sm text-black"
        styles={{
          control: (base) => ({
            ...base,
            border: 'none',
            boxShadow: 'none',
            minHeight: '34px',
          }),
          menu: (base) => ({
            ...base,
            zIndex: 9999
          })
        }}
      />
    </div>
  );
};

export default SkiAreaSelector;
