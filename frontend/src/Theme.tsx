import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {Moon,Sun} from 'lucide-react';

type Theme = 'light'|'dark';
const ThemeContext=createContext<{theme:Theme,setTheme:(theme:Theme)=>void}>({theme:'dark',setTheme:()=>{}});

export function ThemeProvider({children}:{children:ReactNode}){
 const [theme,setTheme]=useState<Theme>(()=>document.documentElement.dataset.theme==='light'?'light':'dark');
 useEffect(()=>{
  document.documentElement.dataset.theme=theme;
  document.documentElement.style.colorScheme=theme;
  try{localStorage.setItem('deepdta-theme',theme)}catch{/* Private browsing can disable storage. */}
 },[theme]);
 useEffect(()=>{
  const sync=(event:StorageEvent)=>{if(event.key==='deepdta-theme'&&(event.newValue==='light'||event.newValue==='dark'))setTheme(event.newValue)};
  window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync);
 },[]);
 return <ThemeContext.Provider value={{theme,setTheme}}>{children}</ThemeContext.Provider>;
}

export function useTheme(){return useContext(ThemeContext)}

export function ThemeToggle(){
 const {theme,setTheme}=useTheme();
 return <div className="theme-switch" role="group" aria-label="Colour theme">
  <span className={`theme-switch-indicator ${theme}`} aria-hidden="true"/>
  <button type="button" aria-label="Light theme" aria-pressed={theme==='light'} title="Light theme" onClick={()=>setTheme('light')}><Sun size={16}/><span>Light</span></button>
  <button type="button" aria-label="Dark theme" aria-pressed={theme==='dark'} title="Dark theme" onClick={()=>setTheme('dark')}><Moon size={16}/><span>Dark</span></button>
 </div>;
}
