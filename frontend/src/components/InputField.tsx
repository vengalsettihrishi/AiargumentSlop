import { Paperclip, ArrowRight } from 'lucide-react';
import { useState } from 'react';

interface InputFieldProps {
  onSubmit: (query: string) => void;
  disabled?: boolean;
}

export default function InputField({ onSubmit, disabled }: InputFieldProps) {
  const [value, setValue] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      onSubmit(value);
      setValue('');
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto pb-8 px-4">
      <form 
        onSubmit={handleSubmit}
        className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl flex items-center p-2 shadow-2xl focus-within:border-[#3A3A3A] transition-colors"
      >
        <button type="button" className="p-3 text-gray-400 hover:text-white transition-colors">
          <Paperclip className="w-5 h-5" />
        </button>
        
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          placeholder="Enter your claim for debate..."
          className="flex-1 bg-transparent text-white placeholder-gray-500 px-2 outline-none disabled:opacity-50"
        />
        
        <button 
          type="submit"
          disabled={!value.trim() || disabled}
          className="bg-primary hover:bg-primaryHover text-black p-3 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <ArrowRight className="w-5 h-5" />
        </button>
      </form>
      <p className="text-center text-xs text-gray-500 mt-4">
        This system uses multi-agent debate and can make mistakes. Verify critical claims.
      </p>
    </div>
  );
}
